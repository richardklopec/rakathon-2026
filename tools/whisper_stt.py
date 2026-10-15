import sys, whisper
model = whisper.load_model("medium", device="cuda")
for wav, lang, out, offset in [(sys.argv[1], "cs", sys.argv[2], 180), (sys.argv[3], "en", sys.argv[4], 7920)]:
    r = model.transcribe(wav, language=lang, fp16=True, condition_on_previous_text=False, verbose=False)
    with open(out, "w", encoding="utf-8") as f:
        for s in r["segments"]:
            t = int(s["start"]) + offset
            f.write(f"[{t//3600}:{t//60%60:02d}:{t%60:02d}] {s['text'].strip()}\n")
    print("done", out, flush=True)
