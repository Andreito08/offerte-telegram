# offerte-telegram

Ogni 10 minuti GitHub Actions legge i canali pubblici `prodigeekOfferte` e `JustTrackIt`,
Claude Haiku (sforzo alto) decide quali offerte sono importanti secondo [criteri.md](criteri.md)
e il bot Telegram manda quelle importanti.

Secrets del repository: `CLAUDE_CODE_OAUTH_TOKEN` (da `claude setup-token`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Finché `criteri.md` contiene "DA COMPILARE" non viene inviato nulla.
