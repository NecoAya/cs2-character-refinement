"""Resumable, manifest-backed CS2 stage runner. Python 3.10+, standard library.

Commands are argv arrays, never shell fragments. Every successful stage is
snapshotted before the next starts. A configured review gate is never auto-accepted.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys

STAGES = ('intake', 'appearance', 'rig', 'firstperson', 'physics', 'hitboxes',
          'holding', 'optimization', 'compile', 'validate', 'package')

def read(p):
    return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))

def save(p, value):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    temporary = p.with_suffix(p.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(temporary, p)

def digest(p):
    h = hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def canonical(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()

def inside(root, relative):
    if not isinstance(relative,str) or not relative:
        raise ValueError('Expected a nonempty relative file path')
    windows = pathlib.PureWindowsPath(relative)
    posix = pathlib.PurePosixPath(relative.replace('\\','/'))
    if windows.drive or windows.root or posix.is_absolute() or '..' in posix.parts or ':' in relative:
        raise ValueError('Unsafe relative file path: '+relative)
    root = pathlib.Path(root).resolve(); p = (root / relative).resolve()
    if p == root or not p.is_relative_to(root): raise ValueError('Path escapes run: '+str(relative))
    return p

def validate(config):
    if not isinstance(config,dict): raise ValueError('Config must be an object')
    if config.get('schema') != 1: raise ValueError('Expected schema 1')
    if config.get('mode') not in ('auto', 'checkpoints'): raise ValueError('Invalid mode')
    stages = config['stages']
    if not isinstance(stages,list) or not all(isinstance(x,dict) for x in stages):
        raise ValueError('Stages must be a list of stage contracts')
    names = [x.get('id') for x in stages]
    if not all(isinstance(n,str) for n in names): raise ValueError('Stage IDs must be strings')
    if not names or len(set(names)) != len(names): raise ValueError('Duplicate/empty stages')
    variables=config.get('variables',{})
    if not isinstance(variables,dict) or {'run','config','skill','python'} & set(variables):
        raise ValueError('Variables cannot override built-in runner paths')
    owned={}
    for s in stages:
        if not re.fullmatch('[a-z][a-z0-9_]*', s['id']): raise ValueError('Invalid stage id')
        if s.get('kind') not in ('command', 'agent'): raise ValueError('Invalid stage kind')
        if not isinstance(s.get('outputs'),list) or not s['outputs']: raise ValueError('Stage requires output contract')
        if s['kind']=='command' and (not isinstance(s.get('argv'),list) or not s['argv']
                                    or not all(isinstance(a,str) for a in s['argv'])):
            raise ValueError('Command requires nonempty argv array')
        for rel in s['outputs']:
            inside(pathlib.Path.cwd()/'contract-root', rel)
            key=pathlib.PurePosixPath(rel.replace('\\','/')).as_posix().casefold()
            first=key.split('/')[0]
            if first in {'config.json','state.json','checkpoints','logs'}:
                raise ValueError('Output conflicts with runner metadata: '+rel)
            if key in owned: raise ValueError('Output already owned by another contract: '+rel)
            if any(key.startswith(k+'/') or k.startswith(key+'/') for k in owned):
                raise ValueError('Output file/directory conflict: '+rel)
            owned[key]=s['id']
    gates=config.get('checkpoints',[])
    if not isinstance(gates,list) or not all(isinstance(g,str) for g in gates):
        raise ValueError('Checkpoints must be a list of stage IDs')
    if not set(gates) <= set(names): raise ValueError('Unknown checkpoint')
    if config['mode']=='auto' and config.get('checkpoints'):
        raise ValueError('Use checkpoints mode for review gates; snapshots are automatic in both modes')
    return config

def start(config_path, run):
    config_path=pathlib.Path(config_path).resolve(); cfg=validate(read(config_path)); run=pathlib.Path(run).resolve()
    if run.exists(): raise ValueError('Run already exists; resume it or choose a fresh directory')
    source=cfg.get('project',{}).get('source')
    if source:
        source=pathlib.Path(source).resolve()
        if source.is_dir() and (run==source or run.is_relative_to(source)):
            raise ValueError('Run must be outside the source directory')
    run.mkdir(parents=True)
    save(run/'config.json',cfg)
    save(run/'state.json',{'schema':1,'config_sha256':canonical(cfg),'config_origin':str(config_path),
         'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed':[],
         'accepted':[], 'pending':None, 'status':'ready','receipts':{}})
    return advance(run)

def load(run):
    run=pathlib.Path(run).resolve(); cfg=validate(read(run/'config.json')); state=read(run/'state.json')
    if canonical(cfg)!=state['config_sha256']: raise ValueError('Config changed; make a new variant run')
    for stage_id,receipt in state['receipts'].items():
        for rel,info in receipt['files'].items():
            archived=inside(run,info['snapshot'])
            if not archived.is_file() or digest(archived)!=info['sha256']:
                raise ValueError('Checkpoint damaged: '+stage_id+'/'+rel)
            current=inside(run,rel)
            if not current.is_file() or digest(current)!=info['sha256']:
                raise ValueError('Completed output edited: '+rel+'; create a variant run')
    return run,cfg,state

def snapshot(run, stage, state, evidence=None):
    files={}
    for rel in stage['outputs']:
        p=inside(run,rel)
        if not p.is_file(): raise ValueError('Missing stage output: '+rel)
        dest=inside(run,'checkpoints/'+stage['id']+'/'+rel)
        dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
        files[rel]={'sha256':digest(p),'bytes':p.stat().st_size,'snapshot':dest.relative_to(run).as_posix()}
    receipt={'files':files,'kind':stage['kind'],'evidence':evidence}
    save(run/'checkpoints'/stage['id']/'receipt.json',receipt)
    state['receipts'][stage['id']]=receipt; state['completed'].append(stage['id'])

def advance(run):
    run,cfg,state=load(run)
    if state['pending']:
        print(json.dumps({'status':state['status'],'pending':state['pending']},ensure_ascii=False)); return 2
    try:
        for s in cfg['stages']:
            if s['id'] in state['completed']: continue
            if s['kind']=='agent':
                state.update(status='needs_authoring',pending=s['id']); save(run/'state.json',state)
                print('NEEDS_AUTHORING '+s['id']+': '+s.get('instruction','See stage contract')); return 2
            variables={'run':str(run),'config':str(run/'config.json'),
                       'skill':str(pathlib.Path(__file__).resolve().parent.parent),
                       'python':sys.executable, **cfg.get('variables',{})}
            argv=[str(a).format_map(variables) for a in s['argv']]
            log=run/'logs'/(s['id']+'.log'); log.parent.mkdir(exist_ok=True)
            state.update(status='running',current=s['id']); save(run/'state.json',state)
            with log.open('wb') as f:
                p=subprocess.run(argv,cwd=run,stdout=f,stderr=subprocess.STDOUT, shell=False)
            if p.returncode: raise ValueError(f"Stage {s['id']} failed ({p.returncode}); {log}")
            if s.get('success_marker') and s['success_marker'] not in log.read_text(encoding='utf8',errors='replace'):
                raise ValueError('Missing success marker: '+s['id'])
            snapshot(run,s,state)
            print('COMPLETE '+s['id'],flush=True)
            if s['id'] in cfg.get('checkpoints',[]):
                state.update(status='awaiting_review',pending=s['id']); save(run/'state.json',state); return 2
            save(run/'state.json',state)
        state.update(status='complete',pending=None,current=None); save(run/'state.json',state)
        print('WORKFLOW_COMPLETE '+str(run)); return 0
    except Exception as e:
        state.update(status='failed',error=str(e)); save(run/'state.json',state); raise

def accept(run,stage,note):
    run,cfg,state=load(run)
    if state['status']!='awaiting_review' or state['pending']!=stage: raise ValueError('Not awaiting this review')
    if not note.strip(): raise ValueError('Record the actual user review or CLI operator decision')
    state['accepted'].append({'stage':stage,'note':note}); state.update(pending=None,status='ready')
    save(run/'state.json',state); return advance(run)

def record(run,stage,evidence):
    run,cfg,state=load(run)
    if state['status']!='needs_authoring' or state['pending']!=stage: raise ValueError('Not awaiting this authoring stage')
    e=read(evidence)
    if not isinstance(e,dict) or not isinstance(e.get('summary'),str) or not e['summary'].strip():
        raise ValueError('Evidence requires a nonempty summary')
    checks=e.get('checks')
    if not isinstance(checks,list) or not checks or not all(
        isinstance(c,dict) and isinstance(c.get('name'),str) and c['name'].strip()
        and c.get('status')=='passed' for c in checks):
        raise ValueError('Evidence requires named checks with passed status')
    if len({c['name'] for c in checks})!=len(checks): raise ValueError('Duplicate evidence check names')
    if e.get('status')!='passed': raise ValueError('Stage evidence must pass actual checks')
    s=next(x for x in cfg['stages'] if x['id']==stage); snapshot(run,s,state,e)
    state.update(pending=None,status='ready')
    if stage in cfg.get('checkpoints',[]): state.update(pending=stage,status='awaiting_review')
    save(run/'state.json',state); return advance(run)

def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('plan'); p.add_argument('config')
    p=sub.add_parser('start'); p.add_argument('config'); p.add_argument('--run',required=True)
    for n in ['resume','status']:
        p=sub.add_parser(n); p.add_argument('run')
    p=sub.add_parser('accept'); p.add_argument('run'); p.add_argument('stage'); p.add_argument('--note',required=True)
    p=sub.add_parser('record'); p.add_argument('run'); p.add_argument('stage'); p.add_argument('--evidence',required=True)
    args=ap.parse_args()
    try:
        if args.cmd=='plan':
            c=validate(read(args.config)); print(json.dumps({'route':c.get('route'),'mode':c['mode'],
                'stages':[{'id':s['id'],'kind':s['kind'],'review':s['id'] in c.get('checkpoints',[])} for s in c['stages']]},indent=2)); return 0
        if args.cmd=='start': return start(args.config,args.run)
        if args.cmd=='resume': return advance(args.run)
        if args.cmd=='status': print(json.dumps(load(args.run)[2],ensure_ascii=False,indent=2)); return 0
        if args.cmd=='accept': return accept(args.run,args.stage,args.note)
        if args.cmd=='record': return record(args.run,args.stage,args.evidence)
    except (ValueError,KeyError,OSError) as e: print('ERROR: '+str(e),file=sys.stderr); return 1

if __name__=='__main__': sys.exit(main())
