import asyncio
from email_service import issue_expired_password_reset

async def test():
    try:
        sent, url = await issue_expired_password_reset(1, 'test@example.com')
        print("Success:", sent, url)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test())

