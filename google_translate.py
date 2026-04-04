import json
from collections import OrderedDict

#from googletrans import Translator

import utils
from correctionDict import correction


def translate(text, is_save=True):
    return text
    with open(utils.translate_path) as f:
        json_datas = json.load(f, object_pairs_hook=OrderedDict)
        modify = correction(text)
        if not modify in json_datas:
            # Instantiates a client
            translator = Translator()

            # Translates some text into Japanese
            translation = translator.translate(modify, dest="ja")

            json_datas[modify] = translation.text

            # 刺繡の繡の修正 というか欠損する
            # json_datas[modify] = json_datas[modify].replace(r'\u7e61',"繍")
            before = json_datas[modify].encode("cp932", "ignore")
            json_datas[modify] = before.decode("cp932")

            if is_save:
                with open(utils.translate_path, "w") as k:
                    json.dump(json_datas, k, indent=2, ensure_ascii=False)

    return json_datas[modify].replace(r"&#39;", "").replace(r"&quot;", "")
