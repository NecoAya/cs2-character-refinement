"""Create a model-independent authoring project without modifying source assets."""
import argparse, copy, pathlib, re, sys
from workflow import read,save,validate,STAGES,digest,inside

SKILL=pathlib.Path(__file__).resolve().parent.parent

def create(identifier,source,workspace,checkpoints=None,hand_manifest=None):
    if not re.fullmatch('[a-z][a-z0-9_]{1,47}',identifier): raise ValueError('Use a 2-48 character lowercase project ID')
    source=pathlib.Path(source).resolve(); workspace=pathlib.Path(workspace).resolve()
    if not source.exists(): raise ValueError('User source does not exist: '+str(source))
    if workspace.exists(): raise ValueError('Project directory exists; choose a fresh directory')
    if source.is_dir() and (workspace==source or workspace.is_relative_to(source)):
        raise ValueError('Workspace must be outside the source directory')
    hand=pathlib.Path(hand_manifest).resolve() if hand_manifest else None
    if hand is not None:
        manifest=read(hand)
        files=manifest.get('files') if isinstance(manifest,dict) else None
        if not isinstance(files,dict) or not files: raise ValueError('Hand manifest requires nonempty files')
        for rel,info in files.items():
            p=inside(hand.parent,rel)
            expected=info.get('sha256') if isinstance(info,dict) else None
            if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
                raise ValueError('Hand manifest requires lowercase SHA256: '+rel)
            if not p.is_file() or digest(p)!=expected: raise ValueError('Hand input changed: '+rel)
    cfg=copy.deepcopy(read(SKILL/'assets/new-character.json'))
    cfg['project'].update(id=identifier,source=str(source),
        source_type='directory' if source.is_dir() else source.suffix.lower(),model_namespace='models/'+identifier)
    cfg['request']['source_root']=str(source)
    cfg['request']['firstperson']['hands']='user_supplied'
    cfg['request']['firstperson']['hand_manifest']=str(hand) if hand else None
    cfg['request']['firstperson']['hand_manifest_sha256']=digest(hand) if hand else None
    cfg['request']['firstperson']['input_status']='manifest_verified' if hand else 'required_before_authoring'
    cfg['checkpoints']=list(dict.fromkeys(checkpoints or []));cfg['mode']='checkpoints' if cfg['checkpoints'] else 'auto'
    validate(cfg);workspace.mkdir(parents=True)
    save(workspace/'project.json',cfg)
    return workspace/'project.json'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--id',required=True)
    p.add_argument('--source',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--checkpoint',action='append',choices=STAGES);p.add_argument('--hand-manifest')
    a=p.parse_args()
    try:
        dest=create(a.id,a.source,a.workspace,a.checkpoint,a.hand_manifest)
        print('PROJECT_CREATED '+str(dest));print('Run workflow.py start <project.json> --run <new run directory> to begin authoring.');return 0
    except (ValueError,OSError,KeyError) as e: p.error(str(e))

if __name__=='__main__':sys.exit(main())
