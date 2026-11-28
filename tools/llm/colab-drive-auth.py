"""Refresh a personal Drive OAuth token and diagnose API access without logging secrets."""
import configparser, datetime, json, os, pathlib, sys
import requests

KNOWN = {
    "accessnotconfigured", "service_disabled", "api_key_service_blocked",
    "insufficientpermissions", "access_token_scope_insufficient",
    "insufficientauthenticationscopes", "forbidden", "permission_denied",
    "ratelimitexceeded", "userratelimitexceeded", "rate_limit_exceeded",
    "dailylimitexceeded", "quotaexceeded", "storagequotaexceeded",
    "resource_exhausted", "appnotauthorizedtofile", "domainpolicy",
    "invalid_grant", "invalid_client", "unauthorized_client",
    "invalid_scope", "access_denied", "invalid_request", "invalidcredentials",
    "unauthenticated", "authentication_error", "notfound", "autherror",
    "backenderror", "internalerror", "consumer_invalid", "consumer_suspended",
    "billing_disabled", "project_deleted", "not_authorized"
}
def fail(phase, response):
    found=set()
    try:
        body=response.json()
        err=body.get("error")
        if isinstance(err,str): found.add(err.lower())
        elif isinstance(err,dict):
            found.add(str(err.get("status","")).lower())
            for key in ("errors","details"):
                for entry in err.get(key,[]):
                    if isinstance(entry,dict): found.add(str(entry.get("reason","")).lower())
    except (ValueError, TypeError, AttributeError): pass
    print("DRIVE_API_ERROR phase="+phase+" http="+str(response.status_code)+" reasons="+",".join(sorted(found & KNOWN) or ["unclassified"]),flush=True)
    raise SystemExit(1)

def main():
    cfg=configparser.ConfigParser(interpolation=None)
    cfg.read_string(os.environ["RCLONE_CONFIG_SECRET"])
    assert cfg.sections()==["rocache"],"Unexpected remote configuration"
    section=cfg["rocache"]
    assert section.get("type")=="drive" and section.get("scope")=="drive.file","Unexpected Drive scope"
    assert all(section.get(k) for k in ("client_id","client_secret")),"Personal OAuth credentials missing"
    old=json.loads(section["token"])
    assert old.get("refresh_token"),"Refresh token missing"
    response=requests.post("https://oauth2.googleapis.com/token",data={
        "client_id":section["client_id"],"client_secret":section["client_secret"],
        "refresh_token":old["refresh_token"],"grant_type":"refresh_token"
    },timeout=30)
    if not response.ok: fail("refresh",response)
    token=response.json()
    expiry=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=int(token["expires_in"]))
    assert token.get("access_token") and token.get("token_type"),"Token response incomplete"
    print("DRIVE_TOKEN_REFRESH: PASS",flush=True)
    response=requests.get("https://www.googleapis.com/drive/v3/files",headers={"Authorization":"Bearer "+token["access_token"]},params={"pageSize":1,"fields":"nextPageToken,files(id)","q":"trashed = false"},timeout=30)
    if not response.ok: fail("files_list",response)
    print("DRIVE_FILES_LIST: PASS",flush=True)
    section["token"]=json.dumps({"access_token":token["access_token"],"token_type":token["token_type"],"refresh_token":token.get("refresh_token") or old["refresh_token"],"expiry":expiry.isoformat().replace("+00:00","Z")})
    p=pathlib.Path(os.environ["RO_CACHE_TMP"])/"drive.conf"
    with p.open("w") as out: cfg.write(out)

if __name__=="__main__":
    try: main()
    except SystemExit: raise
    except Exception as e:
        print("DRIVE_AUTH_LOCAL_ERROR:"+type(e).__name__,flush=True)
        raise SystemExit(1)
