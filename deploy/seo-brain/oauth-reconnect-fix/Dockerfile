FROM seo-brain-backend:20260920-phonetab-v1
COPY backend/seo_brain/connections/google_oauth.py /usr/local/lib/python3.12/site-packages/seo_brain/connections/google_oauth.py
COPY backend/seo_brain/gsc/client.py /usr/local/lib/python3.12/site-packages/seo_brain/gsc/client.py
RUN python -m py_compile /usr/local/lib/python3.12/site-packages/seo_brain/connections/google_oauth.py /usr/local/lib/python3.12/site-packages/seo_brain/gsc/client.py
