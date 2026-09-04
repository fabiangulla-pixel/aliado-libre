"""Servidor HTTP que expone el índice de búsqueda de Aliado Libre por red.

Permite la arquitectura "modelo local + índice en la nube": la app del
usuario corre el LLM en su propia máquina y consulta los ~11GB de índice
en un servidor remoto, en vez de tener que descargarlos y cargarlos."""
