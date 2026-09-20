# Your Japanese Reader — take it to another laptop

1. Copy this WHOLE folder to a USB drive, then to your other Windows laptop.
2. Double-click **Start Reader.cmd**. No installation is needed for reading.
3. Paste Japanese, press **Open text for reading**, and select a word to search.

All 17 dictionary collections from your existing reader are in `dictionaries/`,
including their supplied recordings and other resources. You do not need the
original Downloads folders or dictionary viewer applications.

**Offline translation is now included.** In **Translation engine · 翻譯引擎**,
choose **Argos Translate · offline CPU**, then click **Use selection**. Paste Japanese
and click **Open + translate locally**. You do not need LM Studio or an LLM for Argos.
English is translated directly; Traditional Chinese is translated through English.
Check important wording, especially names and ambiguous sentences.

If you do have LM Studio, choose **LM Studio · local LLM**, select a model and click
**Use selection**. You can switch back to Argos whenever you want.

Keep the new **translation** subfolder: it contains the full offline Argos engine,
models and dependencies. An older Drive upload without this folder will not have Argos.
Re-upload the updated whole folder. Dictionaries and learning prompts still work
independently of translation; prompts can be pasted into any AI chat you use.

Before copying the folder again, click **Save and close reader** and wait for the
launcher window to close. Carry the whole folder, including `data/`, so that your
new texts, translations, notes and preferences come with you. Keep one latest copy;
there is no automatic sync between laptops.

The updated folder is larger because it includes Argos. Allow at least 12 GB free on USB and the destination.
A 16 GB or larger USB drive is suitable. Running from the laptop's internal drive
is faster than a USB stick. This package includes a Windows x64 runtime.

For OBS input, use **Start JP Game Reader.cmd** instead. This optional mode needs
OBS plus Windows Japanese OCR support and a visible windowed projector.

Troubleshooting: keep every subfolder; do not launch from inside an archive. If the
port is occupied, close the other reader. Double-clicking Start Reader again opens
an already running instance of this same library. A command window remains open
while the reader runs; use the reader's close button when finished.
