from app.services.collectors.omdb import OMDbCollector
from app.services.collectors.reddit import RedditCollector
from app.services.collectors.tmdb import TMDBCollector
from app.services.collectors.youtube import YouTubeCollector

__all__ = [
    "TMDBCollector",
    "OMDbCollector",
    "RedditCollector",
    "YouTubeCollector",
]
