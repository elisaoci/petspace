"""Пагинация списков: query-параметры limit/offset и заголовок X-Total-Count.

Формат ответа не меняется (массив), поэтому существующие клиенты продолжают работать.
Клиент видит общее количество в заголовке `X-Total-Count` и листает через limit/offset.
"""

from typing import Annotated

from fastapi import Depends, Query, Response

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Pagination:
    def __init__(
        self,
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Сколько записей вернуть"),
        offset: int = Query(0, ge=0, description="Сколько записей пропустить"),
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationParams = Annotated[Pagination, Depends(Pagination)]


def pagination_headers(response: Response, *, total: int, pagination: Pagination) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(pagination.limit)
    response.headers["X-Offset"] = str(pagination.offset)
