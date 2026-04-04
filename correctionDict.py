def correction(chara):
    # \u00b0 = °(度)　はok
    # \\u00(?!.*e0|e9|e8|e7|ef|ec|f2|f9|a0|cf|f4|c0|c9|eb|ea|e0|ca|ee|c8|e1|e2|b0|c2|ae|e3|ed|e5|c7|fb|d8)[^"]+
    table = str.maketrans({
        u"\u00a0": u" ",  # 謎スペース
        u"\u00e9": u"e",  # Eの修正
        u"\u00e8": u"e",  # Eの修正
        u"\u00e7": u"c",  # cの修正
        u"\u00ef": u"i",  # iの修正
        u"\u00ec": u"i",  # iの修正
        u"\u00f2": u"o",  # oの修正
        u"\u00f9": u"u",  # oの修正

        # 24s限定
        u"\u00cf": u"I",  # Iの修正
        u"\u00f4": u"o",  # oの修正
        u"\u00c0": u"A",  # Aの修正
        u"\u00c9": u"E",  # Eの修正
        u"\u00eb": u"e",  # eの修正
        u"\u00ea": u"e",  # eの修正
        u"\u00e0": u"a",  # aの修正
        u"\u00ca": u"E",  # Eの修正
        u"\u00ee": u"i",  # iの修正
        u"\u00c8": u"E",  # Eの修正
        u"\u00e1": u"a",  # aの修正
        u"\u00e2": u"a",  # aの修正
        u"\u00c2": u"A",  # Aの修正
        u"\u00ae": u"",  # ®の修正
        u"\u00e3": u"a",  # aの修正
        u"\u00ed": u"i",  # iの修正
        u"别": u"別",  # 别の修正
        u"ú": u"u",  # úの修正
        u"ö": u"お",  # öの修正
        u"繡": u"繍",  # 繡の修正

        # なぜか正規表現の検索に引っかからない
        u"\u00ab": u"<",  # iの修正
        u"\u00bb": u">",  # iの修正
        u"\u0153": u"oe",  # oeの修正

        u"\u00e5": u"a",  # aの修正
        u"\u2013": u"-",  # -の修正
        u"\ufffd": u"",  # ハテナの修正
        u"\u2122": u"",  # TMの修正
        u"\u00c7": u"c",  # cの修正
        u"\u00fb": u"u",  # uの修正
        u"\u0178": u"y",  # yの修正
        u"\u2022": u"",  # ・の修正
        u"\u00d8": u"",  # Øの修正
        u"\u00df": u"sz",  # ßの修正
        u"\u00c3": u"a",  # Ãの修正
        u"\u00a9": u"c",  # ©の修正
        u"\u00b2": u"^2",
        u"\u20ac": u"",
        u"Â": u"A",
        u"\ufffc": u"",
        u"\ua4ef": u"V",
        u"\u0152": u"",
        u"\u80f6": u"",
        u"\u916f": u"",
        u"\ube44": u"",
        u"\uc2a4": u"",
        u"\ucf54": u"",
        u"\ud3f4": u"",
        u"\ub9ac": u"",
        u"\uc5d0": u"",
        u"\ud14c": u"",
        u"\ud2bc": u"",
        u"\ub974": u"",
        u"\ufeff": u"",
    })
    modified = chara.translate(table)
    return modified