# Toyota Fiyat Takip

Toyota Türkiye fiyat XML dosyasından `1.5 Dream Multidrive S` modelinin güncel fiyatını takip eder.

## Klasör yapısı

- `src/toyota_fiyat_takip.py`: Ana takip scripti
- `data/fiyat_gecmisi.csv`: Excel'den aktarılan fiyat geçmişi
- `.github/workflows/fiyat-kontrol.yml`: GitHub Actions workflow'u
- `requirements.txt`: Python bağımlılıkları

## Çalışma mantığı

- Saatlik kontrolde fiyat değişmediyse bildirim göndermez.
- Fiyat değişirse CSV'ye kayıt ekler, e-posta ve Telegram bildirimi göndermeyi dener.
- Pazartesi 12:00 Türkiye saati civarında haftalık rapor gönderir.
- Manuel çalıştırmada `change`, `weekly` veya `price` modu seçilebilir.

## GitHub Secrets

- `EMAIL_ENABLED`
- `SMTP_SERVER`
- `SMTP_PORT`
- `EMAIL_USER`
- `EMAIL_PASSWORD`
- `NOTIFICATION_EMAIL`
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

## Test

Actions sekmesinden `Toyota Fiyat Kontrol` workflow'u manuel çalıştırılabilir. İlk test için `price` modu anlık fiyat bildirimi gönderir ve CSV'yi değiştirmez.
