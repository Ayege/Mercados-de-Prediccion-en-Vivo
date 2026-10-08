"""Identidad de la audiencia: entrar con un nombre, demostrar que es tuyo y no abusar.

- Al entrar, el servidor entrega un token aleatorio y guarda solo su SHA-256.
- Si hay código de sala, entrar lo exige: quien no está en la sala no ve el
  código, que solo aparece en la proyección. Así nadie puede llenar la sala ni
  agotar el límite de entradas desde fuera.
- Al entrar, la persona queda asignada a un grupo en cada pregunta con encuadre.
"""
from __future__ import annotations

import hashlib
import secrets

from ..domain.market import Account
from .errors import Conflict, RateLimited, Unauthorized
from .limits import SlidingWindow
from .ports import Repository
from .views import account_view, headline_view

ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I: se dicta en voz alta


def new_room_code(length: int = 6) -> str:
    return "".join(secrets.choice(ROOM_ALPHABET) for _ in range(length))


class Accounts:
    def __init__(self, repo: Repository, starting_balance: float = 1000.0, max_accounts: int = 2000,
                 entries: SlidingWindow | None = None, orders: SlidingWindow | None = None,
                 room_code: str = ""):
        self.repo = repo
        self.starting_balance = starting_balance
        self.max_accounts = max_accounts
        self.entries = entries or SlidingWindow(limit=120, window=60)  # cuentas nuevas por minuto, en total
        self.orders = orders or SlidingWindow(limit=10, window=10)  # órdenes por persona cada 10 s
        self.room_code = room_code.strip().upper()

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def authenticate(self, name: str, token: str) -> Account:
        """La persona demuestra que el nombre es suyo con el token que recibió al entrar.
        Llamar dentro de una transacción."""
        acc = self.repo.get_account(Account.normalize(name))
        if acc is None or not token or not secrets.compare_digest(acc.credential, self._digest(token)):
            raise Unauthorized("token de usuario inválido: vuelve a entrar con otro nombre")
        return acc

    def throttle(self, acc: Account) -> None:
        if not self.orders.allow(acc.name):
            raise RateLimited("demasiadas órdenes seguidas: espera unos segundos")

    def view(self, name: str, token: str) -> dict:
        """La cuenta y, por cada pregunta con titulares, el único titular que esta persona ve.
        Solo lee: el grupo se asignó al entrar o al crear la pregunta."""
        with self.repo.transaction():
            acc = self.authenticate(name, token)
            headlines = {m.id: headline_view(m.headline_for(acc.name))
                         for m in self.repo.markets() if m.framing and m.status == "open"}
            return account_view(acc) | {"headlines": headlines}

    def enter(self, name: str, code: str = "") -> dict:
        """Reserva un nombre y entrega su token. El token se muestra una sola vez."""
        if self.room_code and not secrets.compare_digest(code.strip().upper().encode(),
                                                         self.room_code.encode()):
            raise Unauthorized("código de sala incorrecto: está en la pantalla del proyector")
        name = Account.normalize(name)
        with self.repo.transaction():
            if self.repo.get_account(name) is not None:
                raise Conflict("ese nombre ya está en uso: elige otro")
            if sum(1 for _ in self.repo.accounts()) >= self.max_accounts:
                raise RateLimited("la sala está llena")
            if not self.entries.allow("global"):
                raise RateLimited("están entrando demasiadas personas a la vez: reintenta en un minuto")
            token = secrets.token_urlsafe(24)
            acc = Account(name, self.starting_balance, credential=self._digest(token))
            self.repo.add_account(acc)
            for m in self.repo.markets():
                m.enroll(name)
            return {"name": name, "token": token} | account_view(acc)
