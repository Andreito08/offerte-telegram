"""Legge i canali Telegram pubblici, fa valutare a Haiku le offerte nuove confrontandole con lo
storico prezzi per tipo di prodotto, e manda al bot quelle buone e gli errori di prezzo.
Stato (ultimo post visto) in state.json, storico prezzi in storico.json."""
import html, json, os, re, statistics, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

CHANNELS = ["prodigeekOfferte", "JustTrackIt"]
HERE = Path(__file__).parent
STATE, STORICO = HERE / "state.json", HERE / "storico.json"
UA = {"User-Agent": "Mozilla/5.0"}
MAX_PER_CAT, MAX_GIORNI = 20, 120


def load(p):
    return json.loads(p.read_text(encoding="utf8")) if p.exists() else {}


def save(p, d):
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf8")


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf8")


def parse(page, channel):
    """Ritorna [(id, testo)] dei post nella pagina t.me/s/<canale>."""
    posts = []
    for block in page.split('data-post="')[1:]:
        m = re.match(rf'{re.escape(channel)}/(\d+)"', block, re.I)
        t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
        if m and t:
            text = re.sub(r"<br\s*/?>", "\n", t.group(1))
            text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
            posts.append((int(m.group(1)), text))
    return posts


def stats(prezzi):
    return {"n": len(prezzi), "min": min(prezzi), "mediana": statistics.median(prezzi)} if prezzi else None


def ask_haiku(posts, storico):
    """posts: [(chiave, testo)]. Ritorna {chiave: {cat, prezzo, esito, motivo}}."""
    criteri = (HERE / "criteri.md").read_text(encoding="utf8")
    righe = [f"- {c}: {', '.join(f'{e['p']:g}' for e in v)}" for c, v in storico.items()]
    elenco = "\n\n".join(f"### {k}\n{t[:1500]}" for k, t in posts)
    prompt = f"""Sei un filtro di offerte. Criteri dell'utente:
{criteri}

Storico prezzi recenti per tipo di prodotto (euro, dal più vecchio):
{chr(10).join(righe) or "(vuoto)"}

Offerte nuove:
{elenco}

Per OGNI offerta dai: "k" (la chiave dopo ###), "cat" (tipo di prodotto preciso e confrontabile, es.
"SSD NVMe 2TB", "GPU RX 9060 XT 16GB", "Mouse gaming wireless": se nello storico c'è già un tipo
adatto, riusa ESATTAMENTE quel nome), "prezzo" (numero in euro o null), "esito" ("scarta", "buona"
o "errore" = errore di prezzo), "motivo" (max 15 parole, in italiano).
Rispondi SOLO con un array JSON di oggetti."""
    out = subprocess.run(["claude", "-p", "--model", "haiku", "--effort", "high", prompt],
                         capture_output=True, text=True, encoding="utf8", timeout=600)
    m = re.search(r"\[.*\]", out.stdout, re.S)
    if out.returncode or not m:
        sys.exit(f"Haiku non ha risposto bene: {out.stderr[-500:]} {out.stdout[-500:]}")
    return {r["k"]: r for r in json.loads(m.group(0)) if isinstance(r, dict) and "k" in r}


def da_inviare(r, storico):
    """Applica la regola dello storico: una 'buona' passa solo se non supera la mediana recente."""
    if r.get("esito") == "errore":
        return True
    s = stats([e["p"] for e in storico.get(r.get("cat"), [])])
    p = r.get("prezzo")
    # ponytail: soglia fissa sulla mediana; se arrivano troppe notifiche, abbassala (es. 0.9 * mediana)
    return r.get("esito") == "buona" and not (s and s["n"] >= 3 and p and p > s["mediana"])


def messaggio(k, testo, r, storico):
    s = stats([e["p"] for e in storico.get(r.get("cat"), [])])
    confronto = f"\nStorico {r['cat']}: minimo {s['min']:g}€, mediana {s['mediana']:g}€ ({s['n']} offerte)" if s else ""
    e = html.escape
    if r["esito"] == "errore":
        testa = "🚨🚨🚨 <b>ERRORE DI PREZZO</b> 🚨🚨🚨\n<b>Corri, potrebbe sparire!</b>"
    else:
        testa = "🟢 <b>Buona offerta</b>"
    return f"{testa}\n<i>{e(r.get('motivo', ''))}{e(confronto)}</i>\n\n{e(testo)}\n\nhttps://t.me/{k}"


def send(text):
    data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000],
                                   "parse_mode": "HTML"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", data, timeout=30)


def main():
    state, storico = load(STATE), load(STORICO)
    ripassa = int(os.environ.get("RIPASSA") or 0)  # prova manuale: rivaluta gli ultimi N post per canale
    nuovi = []
    for ch in CHANNELS:
        posts = parse(get(f"https://t.me/s/{ch}"), ch)
        if not posts:
            continue
        ultimo = max(i for i, _ in posts)
        if ch not in state:  # primo giro: parte da adesso, niente arretrati
            state[ch] = ultimo
        start = sorted(i for i, _ in posts)[-ripassa] - 1 if ripassa else state[ch]
        nuovi += [(f"{ch}/{i}", t) for i, t in posts if i > start]
        state[ch] = max(state[ch], ultimo)
    # ponytail: t.me/s mostra ~20 post; se un canale ne pubblica di più in 10 minuti, i più vecchi si perdono
    inviati = 0
    if nuovi:
        esiti = ask_haiku(nuovi, storico)
        oggi = time.strftime("%Y-%m-%d")
        for k, testo in nuovi:
            r = esiti.get(k)
            if not r:
                continue
            print(k, r.get("esito"), r.get("cat"), r.get("prezzo"))
            if da_inviare(r, storico):
                send(messaggio(k, testo, r, storico))
                inviati += 1
            if r.get("cat") and isinstance(r.get("prezzo"), (int, float)) and not ripassa:
                storico.setdefault(r["cat"], []).append({"p": r["prezzo"], "d": oggi})
        limite = time.strftime("%Y-%m-%d", time.localtime(time.time() - MAX_GIORNI * 86400))
        storico = {c: r[-MAX_PER_CAT:] for c, v in storico.items() if (r := [e for e in v if e["d"] >= limite])}
    print(f"nuovi: {len(nuovi)}, inviati: {inviati}")
    save(STATE, state)
    save(STORICO, storico)


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        p = parse('<div data-post="X/5"><div class="tgme_widget_message_text js" dir="auto">A<br/>&amp;B</div></div>', "X")
        assert p == [(5, "A\n&B")], p
        st = {"SSD 2TB": [{"p": 100}, {"p": 120}, {"p": 110}]}
        assert da_inviare({"esito": "buona", "cat": "SSD 2TB", "prezzo": 105}, st)
        assert not da_inviare({"esito": "buona", "cat": "SSD 2TB", "prezzo": 115}, st)
        assert da_inviare({"esito": "errore", "cat": "SSD 2TB", "prezzo": 500}, st)
        assert da_inviare({"esito": "buona", "cat": "Nuovo", "prezzo": 999}, st)
        assert not da_inviare({"esito": "scarta", "cat": "Nuovo", "prezzo": 1}, st)
        assert "ERRORE DI PREZZO" in messaggio("X/5", "a<b", {"esito": "errore", "cat": "SSD 2TB", "motivo": "x"}, st)
        print("ok")
    else:
        main()
