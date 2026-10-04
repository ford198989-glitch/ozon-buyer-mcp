from __future__ import annotations
from pydantic import BaseModel, Field

class Seller(BaseModel):
    name: str | None = None
    rating: float | None = None
    url: str | None = None

class ProductSummary(BaseModel):
    sku: str
    title: str | None = None
    url: str | None = None
    price_rub: int | None = None
    regular_price_rub: int | None = None
    old_price_rub: int | None = None
    discount_text: str | None = None
    rating: float | None = None
    reviews: int | None = None
    brand: str | None = None
    image: str | None = None

class SearchResponse(BaseModel):
    query: str
    sort: str = "popular"
    count: int = 0
    items: list[ProductSummary] = Field(default_factory=list)
    note: str | None = None

class Description(BaseModel):
    text: str = ""
    images: list[str] = Field(default_factory=list)

class ProductDetails(BaseModel):
    sku: str | None = None
    title: str | None = None
    url: str | None = None
    price_rub: int | None = None
    regular_price_rub: int | None = None
    old_price_rub: int | None = None
    available: bool | None = None
    rating: float | None = None
    reviews: int | None = None
    seller: Seller | None = None
    images: list[str] = Field(default_factory=list)
    characteristics: dict[str, str] = Field(default_factory=dict)
    description: Description = Field(default_factory=Description)

class Review(BaseModel):
    author: str | None = None
    score: int | float | None = None
    comment: str = ""
    pros: str = ""
    cons: str = ""
    date: str | None = None
    useful: int | None = None
    purchased: bool | None = None
    has_photos: bool = False

class ReviewsResponse(BaseModel):
    rating: float | None = None
    total_reviews: int | None = None
    count: int = 0
    reviews: list[Review] = Field(default_factory=list)

class PriceResponse(BaseModel):
    sku: str | None = None
    title: str | None = None
    price_rub: int | None = None
    regular_price_rub: int | None = None
    old_price_rub: int | None = None
    available: bool | None = None
    url: str | None = None

class DeliveryResponse(BaseModel):
    product: str
    candidates: list[str] = Field(default_factory=list)
    experimental: bool = True
    note: str = "Delivery data is region/session-dependent."

class CompareItem(BaseModel):
    sku: str | None = None
    title: str | None = None
    price_rub: int | None = None
    regular_price_rub: int | None = None
    old_price_rub: int | None = None
    rating: float | None = None
    reviews: int | None = None
    seller: str | None = None
    available: bool | None = None
    url: str | None = None
    characteristics: dict[str, str] = Field(default_factory=dict)

class CompareResponse(BaseModel):
    count: int = 0
    items: list[CompareItem] = Field(default_factory=list)


class MarketplaceOffer(BaseModel):
    marketplace: str
    product_id: str | None = None
    title: str | None = None
    url: str | None = None
    price_rub: int | None = None
    old_price_rub: int | None = None
    rating: float | None = None
    reviews: int | None = None
    delivery_text: str | None = None
    seller: str | None = None
    image: str | None = None
    relevance: float | None = None
    exact_match: bool = False
    condition: str | None = None
    price_confidence: str | None = None


class MarketplaceSearchResponse(BaseModel):
    query: str
    marketplaces: list[str] = Field(default_factory=list)
    count: int = 0
    offers: list[MarketplaceOffer] = Field(default_factory=list)
    cheapest: MarketplaceOffer | None = None
    errors: dict[str, str] = Field(default_factory=dict)
    note: str | None = None
