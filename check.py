"""Legge i canali Telegram pubblici, fa decidere a Haiku quali offerte sono importanti
e manda quelle importanti al bot. Lo stato (ultimo post visto per canale) sta in state.json."""
import html, json, os, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

CHANNELS = ["prodigeekOfferte", "JustTrackIt"]
HERE = Path(__file__).parent
STATE = HERE / "state.json"
UA = {"User-Agent": "Mozilla/5.0"}


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


def ask_haiku(posts):
    """posts: [(chiave, testo)]. Ritorna l'insieme delle chiavi importanti."""
    criteri = (HERE / "criteri.md").read_text(encoding="utf8")
    elenco = "\n\n".join(f"### {k}\n{t[:1500]}" for k, t in posts)
    prompt = (f"Sei un filtro di offerte. Criteri dell'utente:\n{criteri}\n\n"
              f"Offerte:\n{elenco}\n\nRispondi SOLO con un array JSON delle chiavi (es. "
              f'["canale/123"]) delle offerte importanti secondo i criteri. Nessuna = [].')
    out = subprocess.run(["claude", "-p", "--model", "haiku", "--effort", "high", prompt],
                         capture_output=True, text=True, encoding="utf8", timeout=300)
    m = re.search(r"\[.*?\]", out.stdout, re.S)
    if out.returncode or not m:
        sys.exit(f"Haiku non ha risposto bene: {out.stderr[-500:]} {out.stdout[-500:]}")
    return set(json.loads(m.group(0)))


def send(text):
    data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000]}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", data, timeout=30)


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    nuovi = []
    for ch in CHANNELS:
        posts = parse(get(f"https://t.me/s/{ch}"), ch)
        if not posts:
            continue
        if ch not in state:  # primo giro: parte da adesso, niente arretrati
            state[ch] = max(i for i, _ in posts)
            continue
        nuovi += [(f"{ch}/{i}", t) for i, t in posts if i > state[ch]]
        state[ch] = max(state[ch], max(i for i, _ in posts))
    # ponytail: t.me/s mostra ~20 post; se un canale ne pubblica di più in 10 minuti, i più vecchi si perdono
    if "DA COMPILARE" in (HERE / "criteri.md").read_text(encoding="utf8"):
        nuovi = []  # criteri non ancora scritti: aggiorna solo lo stato
    if nuovi:
        importanti = ask_haiku(nuovi)
        for k, t in nuovi:
            if k in importanti:
                send(f"{t}\n\nhttps://t.me/{k}")
    print(f"nuovi: {len(nuovi)}, inviati: {len(importanti) if nuovi else 0}")
    STATE.write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        p = parse('<div data-post="X/5"><div class="tgme_widget_message_text js" dir="auto">A<br/>&amp;B</div></div>', "X")
        assert p == [(5, "A\n&B")], p
        print("ok")
    else:
        main()
