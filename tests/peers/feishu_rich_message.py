"""Native Feishu/Lark examples from the v4 rich-message normalization contract."""

def sample(kind, app):
    if kind == "sticker":
        return {"message_type":"sticker","content":'{"file_key":"native-sticker-only"}'}, [
            {"type":"text","text":"[原生贴纸]"},
            {"type":"reply","native_id":"om_original"},
        ]
    if kind != "post":
        raise ValueError(f"unknown message example: {kind}")
    import json
    rows = [
        [{"tag":"text","text":"問 @_user_10"}, {"tag":"at","user_id":app},
         {"tag":"a","text":"原連結","href":"https://example.test/manual"}],
        [{"tag":"md","text":"@_user_1"}, {"tag":"code_block","text":"cmd"},
         {"tag":"emotion","emoji_type":"OK"}, {"tag":"img","image_key":"img_original"},
         {"tag":"media","file_key":"file_original"}],
    ]
    body = {"title":"標題","content":rows}
    # Exercise the original direct post and a localized post with the same rows.
    content = body if app == "cli_a" else {"zh_cn":body}
    return {"message_type":"post","content":json.dumps(content)}, [
        {"type":"text","text":"標題\n"}, {"type":"text","text":"問 "},
        {"type":"mention","native":"ou_ten","label":"@Ten"},
        {"type":"mention","native":app,"label":"@Yuki"},
        {"type":"text","text":"原連結 (https://example.test/manual)"}, {"type":"text","text":"\n"},
        {"type":"mention","native":app,"label":"@Yuki"}, {"type":"text","text":"cmd"},
        {"type":"text","text":"[OK]"}, {"type":"media","kind":"image","reference":"img_original"},
        {"type":"media","kind":"video","reference":"file_original"},
        {"type":"reply","native_id":"om_original"},
    ]
