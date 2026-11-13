#!/usr/bin/env python3
"""CPU-friendly Whisper small.en fine-tune: frozen encoder (outputs cached once), LoRA on the decoder.
  python3 train/whisper/train_lora.py --stage cache      # encoder outputs -> train/out/enc_{train,dev}.f16 (memmap)
  python3 train/whisper/train_lora.py --stage train --rank 16 --lr 3e-4 --epochs 2 --tag r16
  python3 train/whisper/train_lora.py --stage export --tag r16   # merge -> HF dir -> ggml f16 -> q5_0
Why decoder-only: drug-name errors are mostly vocabulary/LM errors ("epitropium", "capra"); the encoder (acoustics)
stays stock, which keeps general English and lets one encoder pass serve several LoRA configs.
Training targets use the pipeline's initial prompt as <|startofprev|> context in 70% of items (as at inference)."""
import argparse, json, math, pathlib, random, subprocess, sys, time
import numpy as np, soundfile as sf, torch

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT / "models/hf/whisper-small.en"
OUT = ROOT / "train/out"; OUT.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "train/whisper/data"
torch.set_num_threads(4)


def load_rows(name):
    return [json.loads(l) for l in open(DATA / f"{name}.jsonl")]


def audio(r):
    y, sr = sf.read(ROOT / r["wav"], dtype="float32", start=int(r["start_s"] * 16000), stop=int(r["end_s"] * 16000))
    if y.ndim > 1: y = y.mean(1)
    return y[: 30 * 16000]


def stage_cache(a):
    from transformers import WhisperFeatureExtractor, WhisperForConditionalGeneration
    fe = WhisperFeatureExtractor.from_pretrained(BASE)
    enc = WhisperForConditionalGeneration.from_pretrained(BASE, torch_dtype=torch.float32).model.encoder.eval()
    for name in ("dev", "train"):
        rows = load_rows(name); n = len(rows)
        path = OUT / f"enc_{name}.f16"; done_p = OUT / f"enc_{name}.done"
        mm = np.memmap(path, dtype=np.float16, mode="r+" if path.exists() else "w+", shape=(n, 1500, 768))
        done = int(done_p.read_text()) if done_p.exists() else 0
        t0 = time.time()
        B = 4
        for i in range(done, n, B):
            batch = rows[i:i + B]
            feats = fe([audio(r) for r in batch], sampling_rate=16000, return_tensors="pt").input_features
            with torch.no_grad():
                h = enc(feats).last_hidden_state
            mm[i:i + len(batch)] = h.numpy().astype(np.float16)
            if (i // B) % 25 == 0:
                mm.flush(); done_p.write_text(str(i + len(batch)))
                print(f"{name} {i+len(batch)}/{n} {(time.time()-t0)/max(1,i+len(batch)-done):.2f}s/item", flush=True)
        mm.flush(); done_p.write_text(str(n))
        print("cached", name, n, flush=True)


def build_targets(tok, rows, prompt_ids, p_prompt, seed):
    rng = random.Random(seed)
    sot = tok.convert_tokens_to_ids("<|startoftranscript|>"); nots = tok.convert_tokens_to_ids("<|notimestamps|>"); eot = tok.eos_token_id
    out = []
    for r in rows:
        txt = tok(" " + r["text"].strip(), add_special_tokens=False).input_ids
        pre = prompt_ids if rng.random() < p_prompt else []
        seq = pre + [sot, nots] + txt + [eot]
        seq = seq[-448:]
        inp = seq[:-1]; tgt = seq[1:]
        n_mask = len(pre)   # don't learn to predict the prompt or <|startoftranscript|>
        tgt = [-100] * n_mask + tgt[n_mask:]
        out.append((inp, tgt))
    return out


def lora_model(rank, alpha, dropout):
    from transformers import WhisperForConditionalGeneration
    from peft import LoraConfig, get_peft_model
    m = WhisperForConditionalGeneration.from_pretrained(BASE, torch_dtype=torch.float32)
    tm = r".*decoder\.layers\.\d+\.(self_attn|encoder_attn)\.(q_proj|k_proj|v_proj|out_proj)|.*decoder\.layers\.\d+\.(fc1|fc2)"
    m = get_peft_model(m, LoraConfig(r=rank, lora_alpha=alpha, lora_dropout=dropout, target_modules=tm, bias="none"))
    m.print_trainable_parameters()
    return m


class OnTheFly:
    """Frozen-encoder outputs computed per batch (no disk cache). Indexable like the memmap: enc[list_of_idx]."""
    def __init__(self, rows, encoder):
        from transformers import WhisperFeatureExtractor
        self.rows, self.enc, self.fe = rows, encoder, WhisperFeatureExtractor.from_pretrained(BASE)
    def __getitem__(self, idx):
        feats = self.fe([audio(self.rows[i]) for i in idx], sampling_rate=16000, return_tensors="pt").input_features
        with torch.no_grad():
            return self.enc(feats).last_hidden_state.numpy()


def batches(items, enc, bs, shuffle, seed):
    idx = list(range(len(items)))
    if shuffle: random.Random(seed).shuffle(idx)
    for i in range(0, len(idx), bs):
        b = idx[i:i + bs]
        L = max(len(items[j][0]) for j in b)
        inp = torch.full((len(b), L), 50256, dtype=torch.long); tgt = torch.full((len(b), L), -100, dtype=torch.long); att = torch.zeros((len(b), L), dtype=torch.long)
        for k, j in enumerate(b):
            x, y = items[j]; inp[k, :len(x)] = torch.tensor(x); tgt[k, :len(y)] = torch.tensor(y); att[k, :len(x)] = 1
        e = torch.from_numpy(np.asarray(enc[b], dtype=np.float32))
        yield e, inp, att, tgt


def loss_of(model, e, inp, att, tgt):
    out = model(encoder_outputs=(e,), decoder_input_ids=inp, decoder_attention_mask=att)
    return torch.nn.functional.cross_entropy(out.logits.reshape(-1, out.logits.size(-1)), tgt.reshape(-1), ignore_index=-100)


def stage_train(a):
    from transformers import WhisperTokenizer
    tok = WhisperTokenizer.from_pretrained(BASE)
    prompt = (ROOT / "eval/pipeline_prompt.txt").read_text().strip()
    prompt_ids = [tok.convert_tokens_to_ids("<|startofprev|>")] + tok(" " + prompt, add_special_tokens=False).input_ids[-223:]
    tr_rows, dv_rows = load_rows("train"), load_rows("dev")
    tr = build_targets(tok, tr_rows, prompt_ids, 0.7, 1); dv = build_targets(tok, dv_rows, prompt_ids, 1.0, 2)
    model = lora_model(a.rank, 2 * a.rank, 0.05)
    if (OUT / "enc_train.done").exists() and int((OUT / "enc_train.done").read_text()) == len(tr_rows):
        enc_tr = np.memmap(OUT / "enc_train.f16", dtype=np.float16, mode="r", shape=(len(tr_rows), 1500, 768))
        enc_dv = np.memmap(OUT / "enc_dev.f16", dtype=np.float16, mode="r", shape=(len(dv_rows), 1500, 768))
    else:   # no cache on disk: compute the frozen encoder per batch (LoRA only touches the decoder, so this is identical)
        encoder = model.base_model.model.model.encoder.eval()
        enc_tr, enc_dv = OnTheFly(tr_rows, encoder), OnTheFly(dv_rows, encoder)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=0.01)
    steps = a.epochs * math.ceil(len(tr) / a.bs); warm = max(10, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / warm) * max(0.05, 1 - s / steps))
    log = open(OUT / f"train_{a.tag}.log", "a")

    def evaluate():
        model.eval(); tot = 0; n = 0
        with torch.no_grad():
            for e, inp, att, tgt in batches(dv, enc_dv, a.bs, False, 0):
                l = loss_of(model, e, inp, att, tgt); k = (tgt != -100).sum().item(); tot += l.item() * k; n += k
        model.train(); return tot / max(1, n)
    base_dev = evaluate(); print("dev loss before", round(base_dev, 4), flush=True); log.write(json.dumps(dict(step=0, dev_loss=base_dev)) + "\n")
    best = base_dev; step = 0; t0 = time.time()
    model.train()
    for ep in range(a.epochs):
        for e, inp, att, tgt in batches(tr, enc_tr, a.bs, True, 100 + ep):
            l = loss_of(model, e, inp, att, tgt); l.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step(); opt.zero_grad(); step += 1
            if step % 20 == 0:
                print(f"ep {ep} step {step}/{steps} loss {l.item():.4f} {(time.time()-t0)/step:.2f}s/step", flush=True)
                log.write(json.dumps(dict(step=step, loss=l.item())) + "\n"); log.flush()
        d = evaluate(); print(f"epoch {ep} dev loss {d:.4f} (before {base_dev:.4f})", flush=True)
        log.write(json.dumps(dict(step=step, epoch=ep, dev_loss=d)) + "\n"); log.flush()
        if d < best:
            best = d; model.save_pretrained(OUT / f"lora_{a.tag}")
    json.dump(dict(tag=a.tag, rank=a.rank, lr=a.lr, epochs=a.epochs, bs=a.bs, train_items=len(tr), dev_items=len(dv), dev_loss_before=base_dev, dev_loss_best=best,
                   minutes=(time.time() - t0) / 60), open(OUT / f"train_{a.tag}.json", "w"), indent=1)


def stage_export(a):
    from transformers import WhisperForConditionalGeneration
    from peft import PeftModel
    m = WhisperForConditionalGeneration.from_pretrained(BASE, torch_dtype=torch.float32)
    m = PeftModel.from_pretrained(m, OUT / f"lora_{a.tag}").merge_and_unload()
    hf = OUT / f"hf_{a.tag}"; m.save_pretrained(hf, safe_serialization=False)   # whisper.cpp's converter reads pytorch_model.bin
    for f in ["vocab.json", "merges.txt", "added_tokens.json", "tokenizer_config.json", "special_tokens_map.json", "normalizer.json", "preprocessor_config.json", "generation_config.json"]:
        if (BASE / f).exists(): (hf / f).write_bytes((BASE / f).read_bytes())
    W = ROOT / ".tools/whisper.cpp"
    subprocess.run([sys.executable, str(W / "models/convert-h5-to-ggml.py"), str(hf), "/usr/local/lib/python3.13/site-packages", str(OUT)], check=True)
    f16 = OUT / f"ggml-whisper-ems-small.en-{a.tag}-f16.bin"; (OUT / "ggml-model.bin").rename(f16)
    q5 = ROOT / "models" / f"whisper-ems-small.en-{a.tag}-q5.bin"
    subprocess.run([str(ROOT / ".tools/whisper-quantize"), str(f16), str(q5), "q5_0"], check=True)
    print("wrote", q5)
    # drop the heavy intermediates to save disk (re-creatable from the LoRA adapter)
    for p in (hf / "pytorch_model.bin",): p.unlink(missing_ok=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["cache", "train", "export"])
    ap.add_argument("--rank", type=int, default=16); ap.add_argument("--lr", type=float, default=3e-4); ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--bs", type=int, default=8); ap.add_argument("--tag", default="r16")
    a = ap.parse_args()
    dict(cache=stage_cache, train=stage_train, export=stage_export)[a.stage](a)
