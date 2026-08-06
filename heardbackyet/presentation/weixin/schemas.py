"""Public contract for starting Weixin iLink onboarding."""

from pydantic import BaseModel


class WeixinLoginResponse(BaseModel):
    """Return only the official page that the browser should open."""

    qrcode_url: str
