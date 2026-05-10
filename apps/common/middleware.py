from whitenoise.middleware import WhiteNoiseMiddleware


class MediaAwareWhiteNoiseMiddleware(WhiteNoiseMiddleware):
    """WhiteNoise that skips /media/ URLs so Django can serve uploaded files."""

    def __call__(self, request):
        if request.path.startswith("/media/"):
            return self.get_response(request)
        return super().__call__(request)
