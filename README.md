# offerte-telegram

A ogni giro GitHub Actions legge i canali pubblici `prodigeekOfferte` e `JustTrackIt`,
Claude Haiku (sforzo alto) decide quali offerte nuove sono buone o errori di prezzo secondo
[criteri.md](criteri.md), [preferenze.md](preferenze.md) e lo storico prezzi, e il bot Telegram le manda
(gli errori di prezzo con 🚨). Haiku viene chiamato solo se ci sono post o messaggi nuovi.

- **Avvio**: cron-job.org chiama `workflow_dispatch` ogni pochi minuti, perché la pianificazione `schedule`
  di GitHub su questo repo non è mai partita (resta nel workflow come riserva).
- **Chat**: i messaggi che scrivi al bot vengono letti al giro successivo; Haiku risponde e aggiorna
  `preferenze.md` (indicazioni che hanno la precedenza sui criteri).
- **Storico**: `storico.json`, ultimi 20 prezzi per tipo di prodotto (120 giorni). Una "buona" offerta passa
  solo se non supera la mediana quando ci sono almeno 3 prezzi.
- **Stato**: `state.json` (ultimo post visto, messaggi letti, offerte inviate).
- **Prova**: avvio manuale con `ripassa = N` per rivalutare gli ultimi N post (non tocca lo storico).

Secrets del repository: `CLAUDE_CODE_OAUTH_TOKEN` (da `claude setup-token`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
