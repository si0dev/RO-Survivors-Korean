import inspect,json,os,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parent

def review_one(row,base):
    import json,requests
    prompt=("你是英韩游戏数值与技能效果的语义审校员，不是译者。"
            "独立解析英文和韩文，再比较它们表示的机制，而不是比较相同的数字或单词。\n"
            "检查清单：效果主体、目标、属性、运算方式、数值、单位、持续时间、触发条件、频率、否定、概率、上限和下限。"
            "运算方式必须一致：增加量、减少量、倍率、百分比、绝对值、固定持续时间不能互换。"
            "尤其是简短属性词条：前置 + 或 - 表示相对于原有属性的变化量；"
            "正数持续时间的加成不是一次施加状态的固定持续时间。"
            "例如，某个状态时长增加 2 秒与使目标进入该状态 2 秒是不同机制。"
            "译文即使保留 + 符号和数值，如果语法把变化量改成固定时长，也应拒绝。"
            "同样，不得把增加的伤害值当成最终伤害，不得省略或新增条件。"
            "允许自然的韩语词序和简洁属性标签，不因非实质措辞差异拒绝。\n"
            "只有所有明确的原文机制均被保留且没有新增或冲突含义时输出 ACCEPT。"
            "发现任一明确语义差异或无法确认机制一致时输出 REJECT。"
            "只输出一个英文标签 ACCEPT 或 REJECT，不要翻译、解释或输出其他内容。\n"
            +("这是游戏术语表中的已批准名称，按词义与语境核对，不要求其他措辞逐字相同。若原文是标题或不完整片段，仅验证原文可见内容，不补充上下文。\n" if row.get("terms") or row.get("context") else "")
            +json.dumps({"English":row["source"],"Korean":row["candidate"],**({"Approved terms":row["terms"]} if row.get("terms") else {}),**({"Context":row["context"]} if row.get("context") else {})},ensure_ascii=False))
    try:
        res=requests.post(base+"/v1/chat/completions",
                          json={"messages":[{"role":"user","content":prompt}],
                                "temperature":0,"max_tokens":24,"stream":False,
                                "chat_template_kwargs":{"enable_thinking":False}},
                          timeout=(10,90))
        if res.status_code!=200:
            return "ERROR"
        choice=res.json()["choices"][0]
        verdict=choice["message"]["content"].strip()
        if choice["finish_reason"]!="stop" or verdict not in ("ACCEPT","REJECT"):
            return "INVALID"
        return verdict
    except (requests.RequestException,ValueError,KeyError,IndexError,TypeError,AttributeError):
        return "ERROR"

def build_remote(tmp,payload,marker,preloaded=False):
    cleanup_marker=None
    bootstrap=json.loads((tmp/"bootstrap.json").read_text())
    body="REVIEW_ONLY=True\n"
    if preloaded:
        body+="PRELOADED_MODEL=True\n"
    else:
        body+="CONFIG="+repr(os.environ["REMOTE_CONFIG"])+"\n"
    for key in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA","CACHE_SPEC"):
        body+=key+"="+repr(bootstrap[key])+"\n"
    shared=os.environ.get("RO_REVIEW_SHARED_ROOT")
    if shared:
        body+="REVIEW_SHARED_ROOT="+repr(shared)+"\n"
    if preloaded:
        if not shared: raise RuntimeError("CHAIN_SHARED_SESSION_REQUIRED")
    else:
        for name in ("colab-cache-mount.py","colab-cache.py"):
            body+=(ROOT/name).read_text()+"\n"
    # Explicit process cleanup before the next model in the same VM.
    if shared:
        cleanup_marker=marker+"CLEANUP"
        body+="proc=None; root=None; server_log=None\ntry:\n"
        block=(ROOT/"colab-model.py").read_text()+"\n"+payload
        body+="".join("    "+line+"\n" for line in block.splitlines())
        body+="finally:\n"
        body+="    child=globals().get('proc')\n"
        body+="    if child is not None and child.poll() is None:\n"
        body+="        child.terminate()\n"
        body+="        try: child.wait(timeout=30)\n"
        body+="        except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=30)\n"
        body+="    if globals().get('server_log') is not None: server_log.close()\n"
        body+="    if globals().get('root') is not None: shutil.rmtree(root)\n"
        if not preloaded:
            body+="    pathlib.Path(CONFIG).unlink(missing_ok=True)\n"
            body+="    shutil.rmtree(cache,ignore_errors=True)\n"
        body+="    print("+repr(cleanup_marker)+",flush=True)\n"
    else:
        body+=(ROOT/"colab-model.py").read_text()+"\n"+payload
    return body,cleanup_marker

