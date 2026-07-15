"""Connector configuration endpoints."""

from fastapi import APIRouter, Depends, Query

from researchhub.api.v1.dependencies import get_connector_service
from researchhub.application.services import ConnectorService
from researchhub.domain.schemas import ConnectorCreate, ConnectorRead

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorRead])
async def list_connectors(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ConnectorService = Depends(get_connector_service),
) -> list[ConnectorRead]:
    """List configured metadata connectors."""

    connectors = await service.list_connectors(limit=limit, offset=offset)
    return [ConnectorRead.model_validate(item) for item in connectors]


@router.post("", response_model=ConnectorRead, status_code=201)
async def create_connector(
    payload: ConnectorCreate,
    service: ConnectorService = Depends(get_connector_service),
) -> ConnectorRead:
    """Register an OAI-PMH, OpenAlex, Crossref, DataCite, ORCID, or future connector."""

    connector = await service.create_connector(payload)
    return ConnectorRead.model_validate(connector)

