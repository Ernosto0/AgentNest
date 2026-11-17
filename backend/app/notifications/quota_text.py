"""Fixed texts of the reply-allowance notifications, shared by the external channels.

Like every notification text that leaves the app, these are chosen by type and recipient
language only: they carry no customer text and no workspace-specific value (the numbers are in
the app, one tap away).
"""

TEXT: dict[str, dict[str, tuple[str, str]]] = {
    "quota.warning": {
        "en": (
            "80% of your AI reply allowance is used",
            "See your plan and usage in Settings.",
        ),
        "tr": (
            "Yapay zeka yanıt hakkınızın %80'i kullanıldı",
            "Planınızı ve kullanımı Ayarlar'dan görün.",
        ),
    },
    "quota.grace": {
        "en": (
            "AI reply allowance reached",
            "Drafting continues within an extra 10%, then pauses.",
        ),
        "tr": (
            "Yapay zeka yanıt hakkınıza ulaşıldı",
            "Taslaklar %10 ek hakla devam eder, sonra duraklar.",
        ),
    },
    "quota.paused": {
        "en": (
            "AI replies are paused",
            "Messages still arrive in the inbox. Reply yourself until the next period.",
        ),
        "tr": (
            "Yapay zeka yanıtları duraklatıldı",
            "Mesajlar gelen kutusuna düşmeye devam eder. Yeni döneme kadar kendiniz yanıtlayın.",
        ),
    },
}
