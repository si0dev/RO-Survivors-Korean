"""Read-only probe of the original model cache using personal OAuth; never fetch model bytes."""
import configparser,json,os,pathlib,sys
import requests
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader,module_from_spec

loader=SourceFileLoader("drive_auth",str(pathlib.Path(__file__).with_name("colab-drive-auth.py")))
spec=spec_from_loader(loader.name,loader)
auth=module_from_spec(spec)
loader.exec_module(auth)

def main():
    c=configparser.ConfigParser(interpolation=None)
    c.read(pathlib.Path(os.environ["RO_CACHE_TMP"])/"drive.conf")
    token=json.loads(c["rocache"]["token"])["access_token"]
    def query(name,parent=None):
        q="trashed = false and name = '"+name+"'"
        if parent: q+=" and '"+parent+"' in parents"
        params={"q":q,"fields":"nextPageToken,files(id,mimeType,size,md5Checksum,sha256Checksum)","pageSize":100}
        rows=[]
        while True:
            r=requests.get("https://www.googleapis.com/drive/v3/files",headers={"Authorization":"Bearer "+token},params=params,timeout=30)
            if not r.ok: auth.fail("existing_cache_list",r)
            d=r.json()
            rows+=d.get("files",[])
            if not d.get("nextPageToken"): return rows
            params["pageToken"]=d["nextPageToken"]
    folder="application/vnd.google-apps.folder"
    roots=[x for x in query("RO-Survivors-Korean-cache","root") if x["mimeType"]==folder]
    caches=[x for root in roots for x in query("index-translate-9b-q6k-b12343-v1",root["id"]) if x["mimeType"]==folder]
    name="Index-Translate-9B.Q6_K.gguf"
    models=[x for cache in caches for x in query(name,cache["id"]) if x["mimeType"]!=folder]
    print("EXISTING_CACHE_PATH "+json.dumps({"root_count":len(roots),"cache_count":len(caches),"model_count":len(models)}),flush=True)
    if not models:
        visible=[x for x in query(name) if x["mimeType"]!=folder]
        print("EXISTING_MODEL_NAME_SEARCH "+json.dumps({"visible_count":len(visible)}),flush=True)
        print("EXISTING_CACHE_ACCESS: NOT_VISIBLE",flush=True)
        return
    if len(roots)!=1 or len(caches)!=1 or len(models)!=1:
        print("EXISTING_CACHE_ACCESS: AMBIGUOUS",flush=True)
        return
    model=models[0]
    size=int(model.get("size","0"))
    # A one-byte range confirms actual read access without a full model transfer.
    with requests.get("https://www.googleapis.com/drive/v3/files/"+model["id"],headers={"Authorization":"Bearer "+token,"Range":"bytes=0-0"},params={"alt":"media"},stream=True,timeout=30) as r:
        if not r.ok: auth.fail("existing_model_read",r)
        if r.status_code!=206 or r.headers.get("Content-Range")!="bytes 0-0/"+str(size):
            print("EXISTING_CACHE_ACCESS: RANGE_UNCONFIRMED",flush=True)
            return
        if len(r.raw.read(1))!=1: raise RuntimeError("Empty range response")
    print("EXISTING_CACHE_ACCESS: PASS",flush=True)
    print("EXISTING_MODEL_METADATA "+json.dumps({"size":size,"md5_available":bool(model.get("md5Checksum")),"sha256_available":bool(model.get("sha256Checksum"))}),flush=True)
if __name__=="__main__":
    try: main()
    except SystemExit: raise
    except Exception as e:
        print("EXISTING_CACHE_LOCAL_ERROR:"+type(e).__name__,flush=True)
        sys.exit(1)
