"""OMDb collector: critic/audience scores (IMDb, Rotten Tomatoes, Metacritic)."""

from __future__ import annotations

import re

from app.schemas.dto import RatingDTO, TitleDTO
from app.services.collectors.base import HTTPCollector


def _to_float(value: str | None) -> float | None:
    if not value or value == "N/A":
        return None
    match = re.search(r"[-+]?\d*\.?\d+", value.replace(",", ""))
    return float(match.group()) if match else None


class OMDbCollector(HTTPCollector):
    source = "omdb"
    base_url = "https://www.omdbapi.com"
    rate_bucket = "omdb"

    def __init__(self, settings=None, client=None) -> None:
        super().__init__(settings, client)
        if self.settings.omdb_api_key:
            self.default_params = {"apikey": self.settings.omdb_api_key}

    @property
    def enabled(self) -> bool:
        return bool(self.settings.omdb_api_key)

    async def fetch(self, dto: TitleDTO) -> list[RatingDTO]:
        if not self.enabled:
            return []
        if dto.imdb_id:
            params = {"i": dto.imdb_id}
        else:
            params = {"t": dto.title}
            if dto.year:
                params["y"] = str(dto.year)
        data = await self.get_json("/", params=params, cache_ttl=86400)
        if not data or data.get("Response") == "False":
            return []

        # Backfill the imdb id if we discovered it via title lookup.
        if not dto.imdb_id and data.get("imdbID"):
            dto.imdb_id = data["imdbID"]

        ratings: list[RatingDTO] = []
        imdb_rating = _to_float(data.get("imdbRating"))
        imdb_votes = _to_float(data.get("imdbVotes"))
        if imdb_rating is not None:
            ratings.append(
                RatingDTO(
                    source="imdb",
                    average_rating=imdb_rating,
                    review_count=int(imdb_votes) if imdb_votes else None,
                    audience_score=round(imdb_rating * 10, 1),
                )
            )

        for entry in data.get("Ratings", []):
            src = entry.get("Source")
            val = _to_float(entry.get("Value"))
            if src == "Rotten Tomatoes" and val is not None:
                ratings.append(RatingDTO(source="rotten_tomatoes", critic_score=val))
            elif src == "Metacritic" and val is not None:
                ratings.append(RatingDTO(source="metacritic", critic_score=val))

        metascore = _to_float(data.get("Metascore"))
        if metascore is not None and not any(
            r.source == "metacritic" for r in ratings
        ):
            ratings.append(RatingDTO(source="metacritic", critic_score=metascore))

        return ratings
