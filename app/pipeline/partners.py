"""Довідник ГО/БФ-партнерів для грантів, де ОМС не є прийнятним заявником.

Дані перенесені (адаптовані під наш пайплайн) з довідника `ngoPartners` у
конспекті grantbot (config.js) — користувач вказав його як джерело
концепції/логіки для перенесення. Тут довідник використовується не для
Telegram-розсилки, а для автозаповнення полів `partner_org_*` у
`Grant`, коли `match.py` виставляє `needs_partner_org=True`: підбирається
організація, чия `expertise` найкраще перетинається із сектором/текстом
гранту.

Це евристичний підбір-заглушка (keyword overlap), не остаточне
рішення — рекомендацію завжди варто перевірити вручну перед контактом
з організацією.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NgoPartner:
    name: str
    description: str
    website: str
    contact: str
    expertise: tuple[str, ...]


NGO_PARTNERS: tuple[NgoPartner, ...] = (
    # Львівська область — локальні
    NgoPartner(
        name='Інститут міста',
        description='Урбаністика, публічні простори, розвиток громад Львівщини',
        website='https://mistosite.org.ua',
        contact='info@mistosite.org.ua',
        expertise=('урбаністика', 'публічні простори', 'партисипація'),
    ),
    NgoPartner(
        name='ГО "Сила Громад"',
        description='Допомога ОТГ Львівської області з написанням проєктів та грантів',
        website='https://hromady.org',
        contact='info@hromady.org',
        expertise=('децентралізація', 'розвиток громад', 'грантрайтинг'),
    ),
    # Всеукраїнські організації
    NgoPartner(
        name='ІСАР Єднання',
        description='Найбільший оператор субгрантів для ОГС, навчання, інституційна підтримка',
        website='https://ednannia.ua',
        contact='office@ednannia.ua',
        expertise=('інституційний розвиток', 'субгранти', 'адвокація'),
    ),
    NgoPartner(
        name='Фонд Східна Європа',
        description='Грантова підтримка ГО, адвокація, євроінтеграція на рівні громад',
        website='https://eef.org.ua',
        contact='info@eef.org.ua',
        expertise=('євроінтеграція', 'адвокація', 'місцеве самоврядування'),
    ),
    NgoPartner(
        name='Асоціація міст України (АМУ)',
        description="Міжнародні партнерства, побратимство, допомога з ЄС-проєктами",
        website='https://auc.org.ua',
        contact='office@auc.org.ua',
        expertise=('міжнародне партнерство', 'побратимство', 'євроінтеграція'),
    ),
    NgoPartner(
        name='Transparency International Ukraine',
        description='Прозорість, антикорупція, відкриті дані — часто шукають громади-партнерів',
        website='https://ti-ukraine.org',
        contact='office@ti-ukraine.org',
        expertise=('прозорість', 'відкриті дані', 'антикорупція'),
    ),
    NgoPartner(
        name='Українська Гельсінська спілка з прав людини',
        description='Правозахист, можуть бути партнерами для проєктів з прав людини',
        website='https://helsinki.org.ua',
        contact='office@helsinki.org.ua',
        expertise=('права людини', 'доступ до правосуддя', 'адвокація'),
    ),
    # Міжнародні організації з офісами в Україні
    NgoPartner(
        name='Stowarzyszenie Euroregion Karpacki (Польща)',
        description='Оператор Фонду малих проєктів Interreg PL-UA, пошук польських партнерів',
        website='https://karpacki.pl',
        contact='biuro@karpacki.pl',
        expertise=('транскордонне партнерство', 'interreg', 'польща'),
    ),
    NgoPartner(
        name='SES (Senior Expert Service, Німеччина)',
        description='Безкоштовні експерти-консультанти для громад та бізнесу',
        website='https://www.ses-bonn.de',
        contact='info@ses-bonn.de',
        expertise=('консалтинг', 'менторство', 'capacity building'),
    ),
    NgoPartner(
        name='Habitat for Humanity Ukraine',
        description='Житло, відновлення, shelter — партнер для інфраструктурних проєктів',
        website='https://habitat.org.ua',
        contact='info@habitat.org.ua',
        expertise=('житло', 'відновлення', 'інфраструктура'),
    ),
)


def find_partner(sector: str, raw_text: str = "") -> NgoPartner | None:
    """Підбирає найрелевантнішого партнера за перетином ключових слів.

    Проста keyword-overlap евристика (без LLM), як і решта matching-логіки
    в pipeline/match.py — рекомендація-заглушка, не остаточне рішення.
    """
    haystack = f"{sector} {raw_text}".lower()
    if not haystack.strip():
        return None

    best: NgoPartner | None = None
    best_score = 0
    for partner in NGO_PARTNERS:
        score = sum(1 for kw in partner.expertise if kw in haystack)
        if score > best_score:
            best_score = score
            best = partner

    return best if best_score > 0 else None
