"""Small stable layout examples shared by tests and the golden regenerator."""

from app.content.templates.cards import ResolvedCard
from app.content.templates.spec import BrandRecord

BRAND = BrandRecord(primary_color="#17324d", accent_color="#ffc857", logo_media_asset_id=None)


def sample(template, fmt):
    title, rows = {
        "price_card": ("Aylık üyelik", ("6.000 ₺ / ay",)),
        "hours_card": (
            "Çalışma saatleri",
            ("Pzt–Cum 07:00–23:00", "Cmt 09:00–18:00", "Paz kapalı"),
        ),
        "services_list": ("Hizmetler", ("Üyelik — 6.000 ₺", "Özel ders — 800 ₺")),
        "announcement": (
            "Birlikte güçleniyoruz",
            ("Yeni başlangıçlar için yanınızdayız.\nğĞıİşŞçÇöÖüÜ ₺",),
        ),
    }[template]
    return ResolvedCard(template, fmt, title, rows, "Gölkent İşletmesi")
