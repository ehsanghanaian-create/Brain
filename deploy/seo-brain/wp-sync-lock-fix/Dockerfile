FROM seo-brain-backend:20260921-oauth-reconnect-v2
COPY backend/seo_brain/wordpress/sync.py /usr/local/lib/python3.12/site-packages/seo_brain/wordpress/sync.py
RUN python -m py_compile /usr/local/lib/python3.12/site-packages/seo_brain/wordpress/sync.py
