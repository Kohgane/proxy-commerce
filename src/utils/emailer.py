def send_mail(subject: str, body: str):
    # MVP: 외부 SMTP 필요. 로그로 대체.
    print('[email]', subject, body[:200])
