"""Lease one saved sentence to a browser; accept only unchanged source/results."""
import time,uuid
class Queue:
 def __init__(self,journal):self.journal=journal;self.job=None
 def claim(self,rowid=None):
  if self.job and self.job['deadline']>time.monotonic():return None
  with self.journal.connect() as db:
   if rowid is not None:row=db.execute('SELECT * FROM sentences WHERE id=? AND deleted=0 AND duplicate_of IS NULL',(int(rowid),)).fetchone()
   else:row=db.execute("SELECT * FROM sentences WHERE deleted=0 AND duplicate_of IS NULL AND (english='' OR traditional_chinese='') ORDER BY id DESC LIMIT 1").fetchone()
  if not row:return None
  fields={'en-US':'english','zh-Hant':'traditional_chinese'}
  targets=[lang for lang,field in fields.items() if rowid is not None or not row[field]]
  self.job={'token':uuid.uuid4().hex,'id':row['id'],'text':row['japanese'],'targets':targets,'original':{f:row[f] for f in fields.values()},'deadline':time.monotonic()+190}
  return {k:self.job[k] for k in ['token','id','text','targets']}
 def finish(self,body):
  job=self.job
  if not job or body.get('token')!=job['token']:raise ValueError('Translation expired or belongs to another sentence.')
  if body.get('error'):self.job=None;return False
  results=body.get('translations',{})
  if not isinstance(results,dict) or any(not isinstance(results.get(t),str) or not results[t].strip() or len(results[t])>30000 for t in job['targets']):raise ValueError('Incomplete DeepL translation.')
  fields={'en-US':'english','zh-Hant':'traditional_chinese'}
  changed=0
  with self.journal.connect() as db:
   for target in job['targets']:
    field=fields[target]
    changed+=db.execute(f"UPDATE sentences SET {field}=? WHERE id=? AND japanese=? AND {field}=? AND deleted=0 AND duplicate_of IS NULL",(results[target].strip(),job['id'],job['text'],job['original'][field])).rowcount
  self.job=None
  if changed:self.journal.export_pending.set()
  return bool(changed)
