"""Synthetic coordinator tests: no DCC, game files, network or installation."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import create_project
import workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.writer = self.root / 'writer.py'
        self.writer.write_text(
            'import pathlib,sys\n'
            'p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True)\n'
            'p.write_text("synthetic artifact",encoding="utf8");print("VERIFIED")\n',
            encoding='utf-8')
        self.config_path = self.root / 'project.json'
        self.run = self.root / 'run'

    def config(self):
        return {'schema': 1, 'mode': 'auto', 'checkpoints': [], 'stages': [
            {'id': name, 'kind': 'command', 'argv': ['{python}', str(self.writer), '{run}/'+name+'.txt'],
             'outputs': [name+'.txt'], 'success_marker': 'VERIFIED'} for name in ('first', 'second')]}

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    def start(self, config=None):
        workflow.save(self.config_path, config or self.config())
        return self.quiet(workflow.start, self.config_path, self.run)

    def evidence(self, **updates):
        data = {'status': 'passed', 'summary': 'Synthetic artifact exists',
                'checks': [{'name': 'fixture_exists', 'status': 'passed'}]}
        data.update(updates)
        path = self.root / 'evidence.json'
        workflow.save(path, data)
        return path

    def agent(self, checkpoint=False):
        config = self.config()
        config['stages'][0] = {'id': 'first', 'kind': 'agent', 'outputs': ['first.txt']}
        if checkpoint:
            config.update(mode='checkpoints', checkpoints=['first'])
        self.assertEqual(self.start(config), 2)
        (self.run/'first.txt').write_text('synthetic authored output', encoding='utf-8')

    def test_commands_complete_and_resume(self):
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.quiet(workflow.advance, self.run), 0)
        state = workflow.read(self.run/'state.json')
        self.assertEqual(state['completed'], ['first', 'second'])
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(workflow.digest(self.run/'first.txt'),
                         state['receipts']['first']['files']['first.txt']['sha256'])

    def test_review_cannot_be_bypassed_by_resume_or_wrong_accept(self):
        config = self.config()
        config.update(mode='checkpoints', checkpoints=['first'])
        self.assertEqual(self.start(config), 2)
        self.assertEqual(self.quiet(workflow.advance, self.run), 2)
        self.assertFalse((self.run/'second.txt').exists())
        with self.assertRaises(ValueError):
            workflow.accept(self.run, 'second', 'wrong stage')
        with self.assertRaises(ValueError):
            workflow.accept(self.run, 'first', '   ')
        self.assertEqual(self.quiet(workflow.accept, self.run, 'first', 'Synthetic operator review'), 0)

    def test_agent_record_then_explicit_review(self):
        self.agent(checkpoint=True)
        self.assertEqual(self.quiet(workflow.record, self.run, 'first', self.evidence()), 2)
        self.assertEqual(workflow.read(self.run/'state.json')['status'], 'awaiting_review')
        self.assertFalse((self.run/'second.txt').exists())
        self.assertEqual(self.quiet(workflow.accept, self.run, 'first', 'Synthetic review'), 0)

    def test_invalid_or_failed_evidence_cannot_complete(self):
        self.agent()
        cases = [{'checks': []}, {'checks': ['looks fine']}, {'summary': '  '},
                 {'status': 'not_run'}, {'checks': [{'name': 'check', 'status': 'failed'}]},
                 {'checks': [{'name': 'same', 'status': 'passed'}]*2}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                workflow.record(self.run, 'first', self.evidence(**case))
            self.assertEqual(workflow.read(self.run/'state.json')['completed'], [])

    def test_wrong_record_and_missing_artifact_rejected(self):
        self.agent()
        with self.assertRaises(ValueError):
            workflow.record(self.run, 'second', self.evidence())
        (self.run/'first.txt').unlink()
        with self.assertRaises(ValueError):
            workflow.record(self.run, 'first', self.evidence())

    def test_completed_output_change_detected(self):
        self.start()
        (self.run/'first.txt').write_text('edited', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Completed output edited'):
            workflow.load(self.run)

    def test_snapshot_change_detected(self):
        self.start()
        (self.run/'checkpoints/first/first.txt').write_text('edited', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Checkpoint damaged'):
            workflow.load(self.run)

    def test_config_change_detected(self):
        self.start()
        config = workflow.read(self.run/'config.json')
        config['route'] = 'another route'
        workflow.save(self.run/'config.json', config)
        with self.assertRaisesRegex(ValueError, 'Config changed'):
            workflow.load(self.run)

    def test_command_failure_stops_downstream(self):
        config = self.config()
        config['stages'][0]['argv'] = ['{python}', '-c', 'raise SystemExit(9)']
        with self.assertRaisesRegex(ValueError, 'failed'):
            self.start(config)
        self.assertFalse((self.run/'second.txt').exists())
        self.assertEqual(workflow.read(self.run/'state.json')['status'], 'failed')

    def test_success_marker_and_outputs_are_required(self):
        config = self.config()
        config['stages'][0]['success_marker'] = 'ABSENT'
        with self.assertRaisesRegex(ValueError, 'Missing success marker'):
            self.start(config)
        self.assertFalse((self.run/'second.txt').exists())
        config = self.config()
        config['stages'][0]['outputs'] = ['missing.txt']
        new_run = self.root/'missing-run'
        workflow.save(self.config_path, config)
        with self.assertRaisesRegex(ValueError, 'Missing stage output'):
            self.quiet(workflow.start, self.config_path, new_run)

    def test_output_contracts_reject_escape_metadata_and_collisions(self):
        paths = ['../escape', '/absolute', 'logs/compile.log', 'checkpoints/file',
                 'state.json', 'STATE.JSON', 'config.json', 'state.json/child',
                 'C'+':'+chr(92)+'private', 'named:stream']
        for path in paths:
            config = self.config()
            config['stages'][0]['outputs'] = [path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                workflow.validate(config)
        for path in ('first.txt', 'FIRST.TXT', 'first.txt/child'):
            config = self.config()
            config['stages'][1]['outputs'] = [path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                workflow.validate(config)

    def test_reserved_variables_and_unknown_checkpoints_rejected(self):
        for name in ('run', 'config', 'skill', 'python'):
            config = self.config()
            config['variables'] = {name: 'override'}
            with self.assertRaises(ValueError):
                workflow.validate(config)
        config = self.config()
        config.update(mode='checkpoints', checkpoints=['missing'])
        with self.assertRaises(ValueError):
            workflow.validate(config)

    def test_start_does_not_overwrite_or_write_inside_source(self):
        self.start()
        with self.assertRaises(ValueError):
            workflow.start(self.config_path, self.run)
        source = self.root/'source'
        source.mkdir()
        config = self.config()
        config['project'] = {'source': str(source)}
        workflow.save(self.config_path, config)
        with self.assertRaises(ValueError):
            workflow.start(self.config_path, source/'new-run')
        self.assertEqual(list(source.iterdir()), [])

    def test_cli_reports_authoring_and_status(self):
        config = self.config()
        config['stages'] = [{'id': 'intake', 'kind': 'agent', 'outputs': ['result.json']}]
        workflow.save(self.config_path, config)
        script = Path(workflow.__file__)
        result = subprocess.run([sys.executable, '-B', str(script), 'start', str(self.config_path),
                                 '--run', str(self.run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('NEEDS_AUTHORING intake', result.stdout)
        result = subprocess.run([sys.executable, '-B', str(script), 'status', str(self.run)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('needs_authoring', result.stdout)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'
        self.source.mkdir()
        (self.source/'model.txt').write_text('synthetic source', encoding='utf-8')

    def manifest(self, rel='hand.txt', sha=None):
        hand = self.root/'hand.txt'
        hand.write_text('synthetic hand input', encoding='utf-8')
        path = self.root/'manifest.json'
        workflow.save(path, {'files': {rel: {'sha256': sha or workflow.digest(hand)}}})
        return path

    def test_project_without_bundled_hands_and_all_stages(self):
        source_hash = workflow.digest(self.source/'model.txt')
        path = create_project.create('sample_character', self.source, self.root/'project')
        config = workflow.read(path)
        self.assertEqual([s['id'] for s in config['stages']], list(workflow.STAGES))
        self.assertEqual(config['request']['firstperson']['hands'], 'user_supplied')
        self.assertIsNone(config['request']['firstperson']['hand_manifest'])
        self.assertEqual(config['request']['firstperson']['input_status'], 'required_before_authoring')
        self.assertEqual(config['request']['expressions']['mode'], 'reserve')
        self.assertEqual(workflow.digest(self.source/'model.txt'), source_hash)

    def test_external_hand_manifest_and_checkpoints(self):
        manifest = self.manifest()
        path = create_project.create('sample_character', self.source, self.root/'project',
                                     ['physics', 'physics'], manifest)
        config = workflow.read(path)
        self.assertEqual(config['checkpoints'], ['physics'])
        self.assertEqual(config['mode'], 'checkpoints')
        self.assertEqual(config['request']['firstperson']['hand_manifest_sha256'], workflow.digest(manifest))
        self.assertEqual(config['request']['firstperson']['input_status'], 'manifest_verified')

    def test_all_eleven_template_stages_record_and_snapshot(self):
        project = create_project.create('sample_character', self.source, self.root/'project')
        config = workflow.read(project)
        run = self.root/'run'
        evidence = self.root/'evidence.json'
        workflow.save(evidence, {'status': 'passed', 'summary': 'Synthetic coordinator fixture only',
                                'checks': [{'name': 'fixture_files_exist', 'status': 'passed'}]})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workflow.start(project, run), 2)
            for i, stage in enumerate(config['stages']):
                self.assertEqual(workflow.read(run/'state.json')['pending'], stage['id'])
                for rel in stage['outputs']:
                    workflow.save(run/rel, {'synthetic_fixture': True})
                self.assertEqual(workflow.record(run, stage['id'], evidence),
                                 0 if i == len(config['stages'])-1 else 2)
        state = workflow.load(run)[2]
        self.assertEqual(state['completed'], list(workflow.STAGES))
        self.assertEqual(len(state['receipts']), 11)
        self.assertEqual(state['status'], 'complete')

    def test_manifest_bad_hash_and_path_escape_rejected_before_writes(self):
        for rel, sha in [('hand.txt', '0'*64), ('../escape', '1'*64), ('hand.txt', 'invalid')]:
            manifest = self.manifest(rel, sha)
            with self.subTest(rel=rel, sha=sha), self.assertRaises(ValueError):
                create_project.create('sample_character', self.source, self.root/'project', hand_manifest=manifest)
            self.assertFalse((self.root/'project').exists())
        workflow.save(manifest, {'files': {}})
        with self.assertRaises(ValueError):
            create_project.create('sample_character', self.source, self.root/'project', hand_manifest=manifest)

    def test_invalid_source_workspace_and_id_rejected(self):
        cases = [('InvalidID', self.source, self.root/'project'),
                 ('valid_id', self.root/'missing', self.root/'project'),
                 ('valid_id', self.source, self.source/'nested'),
                 ('valid_id', self.source, self.source)]
        for identifier, source, workspace in cases:
            with self.subTest(identifier=identifier, source=source), self.assertRaises(ValueError):
                create_project.create(identifier, source, workspace)
        with self.assertRaises(ValueError):
            create_project.create('valid_id', self.source, self.root/'project', ['unknown'])
        self.assertFalse((self.root/'project').exists())


if __name__ == '__main__':
    unittest.main()
