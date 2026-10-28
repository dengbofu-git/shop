from django.urls import path
from .pdf_views import artifact

urlpatterns = [
    path('documents/<uuid:document_id>/file', artifact, name='knowledge_pdf_file'),
    path('documents/<uuid:document_id>/pages/<int:page_number>', artifact, name='knowledge_pdf_page'),
]
