【任務】把遊戲腳本抽出成 Japanese Reader 可讀的「台本」格式（個人學習用）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 每次只改這三行 ↓↓↓
遊戲名稱＝CHAOS;CHILD
安裝路徑＝C:\Program Files (x86)\Steam\steamapps\common\CHAOS;CHILD
工作資料夾＝C:\Users\sagen\CC_ScriptExtract
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 背景
我的電腦已連結。我有一個自製的日文閱讀器 Japanese Reader：
C:\Users\sagen\Downloads\Compressed\jp-game-reader-main_2\jp-game-reader-main
它的「台本」分頁會讀取遊戲腳本（搜尋、反白查字典、送 prompt、OCR 自動對照台本並帶入官方譯文）。
我已經用同樣方法抽過 STEINS;GATE RE:BOOT，成品在 C:\Users\sagen\SGRE_ScriptExtract。
**請先讀它的 README.md 和 tools\ 底下的腳本當作範本**（資料夾結構、README 寫法、工具鏈都照它的風格），
再讀閱讀器的 script_library.py，確認你輸出的格式它能直接載入。

這是我自己在 Steam 買的遊戲，只供個人學習。**絕不寫入安裝資料夾（Program Files）**，
只讀取；所有複製、解包、輸出都放在工作資料夾。不要上傳、不要散布抽出的文本。

■ 步驟（照做，不要問我；真的卡住才停下來回報）
1. 偵察：列出安裝資料夾，從檔名、副檔名、封包標頭與 exe 字串判斷是哪個引擎、文本放在哪裡、
   有哪些語言（日文／英文／繁中／簡中，實際有什麼就記什麼，不要假設）。
   不要先入為主：用檔案實際內容確認引擎，再選工具。
2. 選工具：優先用現成的開源解包工具（寫在 README 的出處與版本），下載到 工作資料夾\tools\。
   需要金鑰或解密時，只從遊戲自己的檔案裡找；找不到就停下來，把已知資訊回報給我。
3. 解包到 工作資料夾\raw\，再寫 tools\build_corpus.py 產生 工作資料夾\corpus\script.json。
   解包與建置都要能重跑（README 寫出「How to re-run」兩三行指令）。
4. 驗證（見下方「驗收」），全部通過才算完成。
5. 在閱讀器的 scripts\paths.txt 最後追加一行：工作資料夾\corpus（已經有就不要重複加），
   其他既有內容原樣保留。
6. 在對話裡只報告：引擎與工具、各語言有無、總句數與各 kind 句數、3–5 句樣本、踩過的坑。

■ 輸出格式（必須完全照這個，閱讀器靠它運作）
corpus\script.json（UTF-8，ensure_ascii=False）：
```json
{
  "game": "CHAOS;CHILD",
  "note": "zh is Traditional Chinese ...（說明各欄位實際是什麼語言）",
  "languages": {"ja": true, "en": true, "zh_Hant": false, "zh_Hans": false},
  "stats": {"total": 0, "by_kind": {}, "missing_ja": 0, "missing_en": 0, "missing_zh": 0, "built_utc": "..."},
  "rows": [
    {"source": "script/xxx.scx", "id": "block/0001", "kind": "dialogue",
     "speaker": "有村雛絵", "voice": "",
     "ja": "學習用日文", "en": "", "zh": "", "zh_hans": "",
     "ja_raw": "保留 ruby／原始標記的日文", "en_raw": "", "zh_raw": ""}
  ]
}
```
規則：
- **rows 的順序＝故事順序**（依章節／腳本執行順序排，不是依檔名亂序）。閱讀器用列序當句號 #1、#2…，之後不能再改。
- source＋"|"＋id 必須**全域唯一且穩定**（重建後同一句的 key 不變；用檔案路徑＋腳本內的標籤／索引，不要用流水號）。
- kind 只用這五種：dialogue（台詞與旁白）、mail（郵件／簡訊／聊天）、tip（TIPS／名詞解說）、ui（介面文字）、extra（其他）。
- ja 是「乾淨的學習文字」：
  ・ruby 只留本文（例如 [かんじ]漢字 → 漢字；原樣放在 ja_raw）
  ・移除引擎控制碼（顏色、等待、換頁、音效、變數等）；真正的換行用 \n
  ・TIPS 用語若腳本有標記，可以寫成 <tips,編號,用語>，閱讀器會顯示成底線字
  ・日文原文不得改寫或潤飾
- speaker：有就填角色名（日文），沒有留空字串。旁白＝空字串。
- 沒有的語言填空字串，languages 標 false；不要用機器翻譯補。
- 同一句在多個語言槽位時，靠腳本內的固定索引對齊，不要模糊比對。
- 跳過除錯／測試腳本，並寫進 README 的 Dead ends。
- "game" 要和遊戲視窗標題一致（例如 CHAOS;CHILD），閱讀器靠它自動選 OCR 對照台本。

■ 驗收（寫成 tools\verify_corpus.py，全部通過才算完成）
- JSON 能載入；每列都有上述 12 個欄位且都是字串。
- key 無重複；ja 非空比例 ≥ 95%（dialogue）。
- ja 裡不殘留引擎控制碼：用 regex 掃 [ ] { } % @ \ 等可疑標記與 ASCII 控制字元，列出殘留數量與前 10 例（<tips,…> 除外）。
- 印出每種 kind 的數量，以及開頭、中間、結尾各 3 句樣本（source|id、speaker、ja、en、zh）。
- 用閱讀器本身驗證載入與搜尋（把 閱讀器路徑 加進 sys.path）：
  python -c "import os,sys;sys.path.insert(0,r'<閱讀器路徑>');os.environ['JP_READER_SCRIPTS']=r'<工作資料夾>\corpus';import script_library as s;x=s.Library().refresh()[0];print(x.info());print(x.search('の')['total'])"
- 用 journal.py 的 Matcher 測 OCR 對照：拿 3 句 ja 故意改掉一個假名或標點，match() 應該回傳原句且 confidence ≥ 0.92。

■ 另外寫 README.md（照 SGRE 的格式）
遊戲／引擎表、語言表、統計、對齊用的 key 規則、如何重跑、Dead ends、樣本句。
開頭註明：Personal use only. Do not redistribute.
