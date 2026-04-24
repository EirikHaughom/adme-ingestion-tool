import { joinSession } from "@github/copilot-sdk/extension";

// OSDU/ADME API Reference — M25 Release
// Source: https://github.com/microsoft/adme-samples/tree/main/rest-apis/M25

const OSDU_APIS = {
  storage: {
    title: "Storage Service",
    version: "2.0",
    basePath: "/api/storage/v2",
    description:
      "Core record CRUD service. Manages records (create, read, update, delete) in the OSDU data platform. Every piece of data in ADME is a record managed by Storage.",
    auth: "Bearer token in Authorization header. Header: data-partition-id (required).",
    roles: {
      create: "service.storage.creator or service.storage.admin",
      read: "service.storage.viewer or service.storage.creator or service.storage.admin",
      delete: "service.storage.creator or service.storage.admin",
      purge: "service.storage.admin",
    },
    endpoints: [
      {
        method: "PUT",
        path: "/records",
        operationId: "createOrUpdateRecords",
        summary: "Create or update records in batch (up to 500).",
        requestBody: {
          type: "array",
          items: "Record",
          description:
            "Array of Record objects. Each record must have: id (pattern: partition:kind:unique-id), kind, acl {owners, viewers}, legal {legaltags, otherRelevantDataCountries}, data (object with at least 1 property).",
        },
        response: {
          type: "CreateUpdateRecordsResponse",
          fields: "recordCount, recordIds, recordIdVersions, skippedRecordIds",
        },
        notes:
          "Upserts records. If record id exists, creates a new version. skipdupes=true query param skips records with identical content.",
      },
      {
        method: "GET",
        path: "/records/{id}",
        operationId: "getRecord",
        summary: "Get a specific record by id.",
        params: [
          "id (path) - Record id",
          "attribute (query, optional) - Filter attributes to return",
        ],
        response: "Full Record object with version, data, acl, legal, meta, tags, ancestry",
      },
      {
        method: "GET",
        path: "/records/versions/{id}",
        operationId: "getRecordVersions",
        summary: "List all versions of a record.",
        response:
          "DatastoreQueryResult with cursor and results (list of version numbers)",
      },
      {
        method: "GET",
        path: "/records/{id}/{version}",
        operationId: "getSpecificRecordVersion",
        summary: "Get a specific version of a record.",
      },
      {
        method: "POST",
        path: "/query/records",
        operationId: "fetchRecords",
        summary: "Fetch multiple records by id (batch GET, up to 100).",
        requestBody: {
          type: "MultiRecordIds",
          fields: "records (array of ids, max 100), attributes (optional filter)",
        },
        response:
          "MultiRecordInfo with records array, invalidRecords, retryRecords",
      },
      {
        method: "POST",
        path: "/query/records:batch",
        operationId: "fetchRecordsBatch",
        summary: "Batch fetch records (up to 20 at a time).",
        requestBody: {
          type: "MultiRecordRequest",
          fields: "records (array of ids, max 20)",
        },
      },
      {
        method: "POST",
        path: "/records/delete",
        operationId: "softDeleteRecord",
        summary: "Soft delete a record (marks as deleted, still recoverable).",
      },
      {
        method: "DELETE",
        path: "/records/{id}",
        operationId: "purgeRecord",
        summary:
          "Permanently delete a record and all its versions. Requires admin role.",
      },
      {
        method: "GET",
        path: "/query/kinds",
        operationId: "getKinds",
        summary: "List all kinds in the data partition. Supports cursor pagination.",
        params: ["cursor (query, optional)", "limit (query, optional, default 10)"],
      },
      {
        method: "PATCH",
        path: "/records",
        operationId: "patchRecords",
        summary:
          "Bulk update metadata (acl, legal, tags) across multiple records using JSON Patch operations.",
        requestBody: {
          type: "PatchRecordsRequestModel",
          fields: "ops (JSON Patch array), query (RecordQueryPatch with ids array)",
          example:
            '{ "ops": [{"op": "replace", "path": "/acl/viewers", "value": ["data.default.viewers@partition.dataservices.energy"]}], "query": {"ids": ["partition:kind:id1"]} }',
        },
      },
    ],
    recordStructure: {
      id: "Format: {data-partition-id}:{kind-sub-type}:{unique-id}. Example: opendes:work-product-component--WellLog:abc123",
      kind: "Format: {authority}:{source}:{entity-type}:{version}. Example: osdu:wks:work-product-component--WellLog:1.4.0",
      acl: {
        owners:
          "Array of data group emails, e.g. ['data.default.owners@opendes.dataservices.energy']",
        viewers:
          "Array of data group emails, e.g. ['data.default.viewers@opendes.dataservices.energy']",
      },
      legal: {
        legaltags:
          "Array of legal tag names, e.g. ['opendes-private-usa-dataset-1']",
        otherRelevantDataCountries: "Array of ISO country codes, e.g. ['US']",
      },
      data: "Object containing the domain-specific record payload (must have at least 1 property)",
      ancestry: "Optional. { parents: ['partition:kind:parent-id:version'] }",
      tags: "Optional key-value metadata tags",
      meta: "Optional array of metadata objects",
    },
  },

  search: {
    title: "Search Service",
    version: "2.0",
    basePath: "/api/search/v2",
    description:
      "Full-text search service backed by Elasticsearch. Supports text search, range queries, geo-spatial filters, aggregations, and cursor-based pagination for large result sets.",
    auth: "Bearer token. Header: data-partition-id (required).",
    roles: "users.datalake.viewers or users.datalake.editors or users.datalake.admins or users.datalake.ops. Users must also be in the relevant data groups.",
    endpoints: [
      {
        method: "POST",
        path: "/query",
        operationId: "queryRecords",
        summary: "Search records with offset-based pagination (max 10,000 results).",
        requestBody: {
          type: "QueryRequest",
          fields: {
            kind: "(required) Object — the kind(s) to search",
            query: "Lucene query string, e.g. 'data.WellName:\"North Sea Well*\"'",
            limit: "Max results per page (default varies, typically 10-100)",
            offset: "Offset for pagination",
            returnedFields: "Array of field paths to return",
            sort: "{ field: ['data.Name'], order: ['ASC'] }",
            spatialFilter: "Geo filter: byBoundingBox, byDistance, byGeoPolygon, byIntersection, byWithinPolygon",
            aggregateBy: "Field to aggregate by",
            queryAsOwner: "Boolean — search as owner",
            trackTotalCount: "Boolean — return accurate total count",
          },
        },
        response: {
          type: "QueryResponse",
          fields: "results (array of record objects), totalCount, aggregations, phraseSuggestions",
        },
      },
      {
        method: "POST",
        path: "/query_with_cursor",
        operationId: "queryWithCursor",
        summary:
          "Search with cursor-based pagination. Use for large result sets (no 10k limit). Returns a cursor for the next page.",
        requestBody: {
          type: "CursorQueryRequest",
          fields: {
            kind: "(required) Object — kind(s) to search",
            query: "Lucene query string",
            cursor: "Cursor from previous response (omit for first page)",
            limit: "Results per page",
            returnedFields: "Fields to return",
            sort: "Sort specification",
            spatialFilter: "Geo filter",
          },
        },
        response: {
          type: "CursorQueryResponse",
          fields: "results (array), cursor (string for next page), totalCount",
        },
        notes:
          "Preferred for data export/sync workflows. Keep calling with returned cursor until cursor is null or results are empty.",
      },
      {
        method: "DELETE",
        path: "/query_with_cursor/{cursor}",
        operationId: "closeCursor",
        summary: "Close an open cursor to release server resources.",
      },
    ],
    queryExamples: [
      {
        description: "Search all WellLog records",
        body: '{ "kind": "*:*:*:*", "query": "kind:\\\"osdu:wks:work-product-component--WellLog:*\\\"", "limit": 100 }',
      },
      {
        description: "Search by specific field value",
        body: '{ "kind": "osdu:wks:master-data--Well:*", "query": "data.FacilityName:\\"My Well\\"", "returnedFields": ["id", "data.FacilityName"] }',
      },
      {
        description: "Cursor-based export of all records of a kind",
        body: '{ "kind": "osdu:wks:work-product-component--WellLog:1.4.0", "limit": 1000 }',
      },
    ],
  },

  schema: {
    title: "Schema Service",
    version: "1.0",
    basePath: "/api/schema-service/v1",
    description:
      "Centralized schema governance. Manages JSON schemas that define the structure of records. Schemas have lifecycle states: DEVELOPMENT → PUBLISHED → OBSOLETE.",
    auth: "Bearer token. Header: data-partition-id (required).",
    roles: {
      read: "service.schema-service.viewers",
      write: "service.schema-service.editors",
    },
    endpoints: [
      {
        method: "GET",
        path: "/schema",
        operationId: "getSchemaInfoList",
        summary: "List/search available schemas with filters.",
        params: [
          "authority (e.g. 'osdu')",
          "source (e.g. 'wks')",
          "entityType (e.g. 'wellbore')",
          "schemaVersionMajor, schemaVersionMinor, schemaVersionPatch",
          "status (PUBLISHED, DEVELOPMENT, OBSOLETE)",
          "scope (INTERNAL, SHARED)",
          "latestVersion (True/False)",
          "limit (max 100), offset",
        ],
        response: "SchemaInfoResponse: { count, offset, totalCount, schemaInfos[] }",
      },
      {
        method: "GET",
        path: "/schema/{id}",
        operationId: "getSchema",
        summary: "Get the full JSON schema definition by schema id.",
        params: ["id (e.g. 'osdu:wks:wellbore:1.0.0')"],
        response: "JSON Schema object (draft-07)",
      },
      {
        method: "POST",
        path: "/schema",
        operationId: "createSchema",
        summary: "Create a new schema. The schemaIdentity must be unique.",
      },
      {
        method: "PUT",
        path: "/schema",
        operationId: "upsertSchema",
        summary:
          "Create or update a DEVELOPMENT schema. Cannot modify PUBLISHED/OBSOLETE schemas.",
      },
    ],
    schemaIdentity: {
      format: "{authority}:{source}:{entityType}:{major}.{minor}.{patch}",
      example: "osdu:wks:wellbore:1.0.0",
      fields:
        "authority (e.g. osdu), source (e.g. wks), entityType (e.g. wellbore), schemaVersionMajor, schemaVersionMinor, schemaVersionPatch",
    },
  },

  legal: {
    title: "Legal/Compliance Service",
    version: "1.0.0",
    basePath: "/api/legal/v1",
    description:
      "Manages LegalTags for data governance. Every record must reference a valid LegalTag. LegalTags define data classification, country of origin, export controls, and contract associations.",
    auth: "Bearer token. Header: data-partition-id (required).",
    endpoints: [
      {
        method: "GET",
        path: "/legaltags",
        operationId: "listLegalTags",
        summary: "List all LegalTags. Optionally filter by validity.",
        params: ["valid (boolean, default true)"],
      },
      {
        method: "POST",
        path: "/legaltags",
        operationId: "createLegalTag",
        summary: "Create a LegalTag (must be created before ingesting data).",
        requestBody: {
          type: "LegalTagDto",
          fields: {
            name: "e.g. 'OSDU-Private-EHCData'",
            description: "Human-readable description",
            properties: {
              contractId: "Contract reference",
              countryOfOrigin: "Array of ISO country codes",
              dataType: "Data type classification",
              securityClassification: "Security level",
              exportClassification: "Export control",
              personalData: "Personal data indicator",
              expirationDate: "ISO date format",
            },
          },
        },
      },
      {
        method: "GET",
        path: "/legaltags/{name}",
        operationId: "getLegalTag",
        summary: "Get a specific LegalTag by name.",
      },
      {
        method: "PUT",
        path: "/legaltags",
        operationId: "updateLegalTag",
        summary: "Update a LegalTag's properties.",
      },
      {
        method: "DELETE",
        path: "/legaltags/{name}",
        operationId: "deleteLegalTag",
        summary: "Delete a LegalTag (makes associated data invalid).",
      },
      {
        method: "POST",
        path: "/legaltags:batchRetrieve",
        operationId: "getLegalTags",
        summary: "Batch retrieve up to 25 LegalTags by name.",
      },
      {
        method: "POST",
        path: "/legaltags:validate",
        operationId: "validateLegalTags",
        summary: "Validate LegalTags and get reasons for invalidity.",
      },
      {
        method: "GET",
        path: "/legaltags:properties",
        operationId: "getLegalTagProperties",
        summary: "Get allowed values for LegalTag fields (countries, data types, etc.).",
      },
    ],
  },

  entitlements: {
    title: "Entitlements Service",
    version: "2.0",
    basePath: "/api/entitlements/v2",
    description:
      "Authorization service. Manages groups (DATA, USER, SERVICE) and their memberships. Controls who can access what data via ACL references to data groups.",
    auth: "Bearer token. Header: data-partition-id (required).",
    endpoints: [
      {
        method: "GET",
        path: "/groups",
        operationId: "listGroups",
        summary: "List all groups the caller belongs to.",
      },
      {
        method: "POST",
        path: "/groups",
        operationId: "createGroup",
        summary: "Create a new group.",
        requestBody: {
          type: "CreateGroupDto",
          fields: "name (pattern: ^[A-Za-z0-9{}_.-]{3,128}$), description (optional)",
        },
      },
      {
        method: "POST",
        path: "/groups/{group_email}/members",
        operationId: "addMember",
        summary: "Add a member (USER or GROUP) to a group with role MEMBER or OWNER.",
      },
      {
        method: "GET",
        path: "/groups/{group_email}/members",
        operationId: "listGroupMembers",
        summary: "List members of a group.",
      },
      {
        method: "DELETE",
        path: "/groups/{group_email}/members/{member_email}",
        operationId: "deleteMember",
        summary: "Remove a member from a group.",
      },
      {
        method: "DELETE",
        path: "/groups/{group_email}",
        operationId: "deleteGroup",
        summary: "Delete a group entirely.",
      },
    ],
    groupTypes: {
      DATA: "Controls data access. Referenced in record ACLs. Format: data.{name}@{partition}.dataservices.energy",
      USER: "Controls user permissions. Format: users.{name}@{partition}.dataservices.energy",
      SERVICE: "Controls service-level access. Format: service.{name}@{partition}.dataservices.energy",
    },
  },

  workflow: {
    title: "Workflow/Ingestion Service",
    version: "2.0.5",
    basePath: "/api/workflow",
    description:
      "Orchestration service wrapping Apache Airflow. Manages workflow definitions (DAGs) and their execution runs. Used for CSV ingestion, manifest-based ingestion, and custom workflows.",
    auth: "Bearer token. Header: data-partition-id (required).",
    roles: {
      view: "service.workflow.viewer",
      create: "service.workflow.creator",
      admin: "service.workflow.admin",
    },
    endpoints: [
      {
        method: "GET",
        path: "/v1/workflow",
        operationId: "getAllWorkflowsForTenant",
        summary: "List all workflows for the tenant.",
        params: ["prefix (optional filter)"],
      },
      {
        method: "POST",
        path: "/v1/workflow",
        operationId: "create",
        summary: "Create a new workflow definition.",
        requestBody: {
          type: "CreateWorkflowRequest",
          fields: "workflowName, description, registrationInstructions (DAG config)",
        },
      },
      {
        method: "GET",
        path: "/v1/workflow/{workflow_name}",
        operationId: "getWorkflowByName",
        summary: "Get workflow details by name.",
      },
      {
        method: "POST",
        path: "/v1/workflow/{workflow_name}/workflowRun",
        operationId: "triggerWorkflow",
        summary: "Trigger a workflow run.",
        requestBody: {
          type: "TriggerWorkflowRequest",
          fields: "executionContext (key-value map for DAG config), runId (optional)",
        },
        response: "WorkflowRunResponse: { runId, workflowId, status, startTimeStamp }",
      },
      {
        method: "GET",
        path: "/v1/workflow/{workflow_name}/workflowRun/{runId}",
        operationId: "getWorkflowRunById",
        summary: "Get status of a specific workflow run.",
        response:
          "WorkflowRunResponse with status: SUBMITTED | INPROGRESS | SUCCESS | PARTIAL_SUCCESS | FAILED",
      },
      {
        method: "PUT",
        path: "/v1/workflow/{workflow_name}/workflowRun/{runId}",
        operationId: "updateWorkflowRun",
        summary: "Update workflow run status.",
      },
      {
        method: "DELETE",
        path: "/v1/workflow/{workflow_name}",
        operationId: "deleteWorkflowById",
        summary: "Delete a workflow definition.",
      },
    ],
    commonWorkflows: [
      "osdu_ingest — Manifest-based ingestion workflow",
      "csv_parser — CSV file ingestion",
      "Osdu_ingest — OSDU standard ingestion",
    ],
  },

  file: {
    title: "File Service",
    version: "2.0.0",
    basePath: "/api/file",
    description:
      "Manages file uploads, downloads, and metadata. Files are stored in a landing zone and linked to metadata records via FileSource.",
    auth: "Bearer token. Header: data-partition-id (required).",
    roles: {
      upload: "service.file.editors (or users.datalake.editors/admins/ops)",
      download: "service.file.viewers (or users.datalake.viewers/editors/admins/ops)",
      delete: "users.datalake.editors or users.datalake.admins",
    },
    endpoints: [
      {
        method: "GET",
        path: "/v2/files/uploadURL",
        operationId: "getLocationFile",
        summary:
          "Get a signed URL to upload a file. Returns FileSource for linking to metadata. URL valid for 1 hour (max 7 days).",
        params: ["expiryTime (e.g. '5M', '1H', '1D')"],
        response: "LocationResponse: { FileID, Location: { SignedURL, FileSource } }",
      },
      {
        method: "POST",
        path: "/v2/files/metadata",
        operationId: "postFilesMetadata",
        summary:
          "Create metadata record for an already-uploaded file. Links via FileSource in data.DatasetProperties.FileSourceInfo.",
        requestBody: {
          type: "FileMetadata",
          fields:
            "kind (e.g. osdu:wks:dataset--File.Generic:1.0.0), acl, legal, data (FileData with DatasetProperties.FileSourceInfo)",
        },
      },
      {
        method: "GET",
        path: "/v2/files/{id}/downloadURL",
        operationId: "downloadURL",
        summary: "Get a signed URL to download a file. URL valid for 1 hour (max 7 days).",
      },
      {
        method: "GET",
        path: "/v2/files/{id}/metadata",
        operationId: "getFileMetadataById",
        summary: "Get file metadata record by id.",
      },
      {
        method: "DELETE",
        path: "/v2/files/{id}/metadata",
        operationId: "deleteFileMetadataById",
        summary: "Delete file metadata and the associated file.",
      },
    ],
    uploadFlow: [
      "1. GET /v2/files/uploadURL → get SignedURL and FileSource",
      "2. PUT the file content to the SignedURL (Azure Blob SAS URL)",
      "3. POST /v2/files/metadata with FileSource in the record body",
    ],
  },

  dataset: {
    title: "Dataset Service",
    version: "1.0.0",
    basePath: "/api/dataset/v1",
    description:
      "Manages dataset registries and provides storage/retrieval instructions (signed URLs) for datasets. Works with various dataset types (File.Generic, etc.).",
    auth: "Bearer token. Header: data-partition-id (required).",
    endpoints: [
      {
        method: "POST",
        path: "/storageInstructions",
        operationId: "storageInstructions",
        summary: "Get signed URL for uploading a dataset.",
        params: ["kindSubType (e.g. 'dataset--File.Generic')", "expiryTime (optional)"],
      },
      {
        method: "PUT",
        path: "/registerDataset",
        operationId: "createOrUpdateDatasetRegistry",
        summary: "Create or update dataset registry entries (up to 20).",
      },
      {
        method: "GET",
        path: "/getDatasetRegistry",
        operationId: "getDatasetRegistry",
        summary: "Get a dataset registry by id.",
      },
      {
        method: "GET",
        path: "/retrievalInstructions",
        operationId: "retrievalInstructions",
        summary: "Get signed URL(s) for downloading a dataset.",
      },
    ],
  },

  indexer: {
    title: "Indexer Service",
    version: "2.0",
    basePath: "/api/indexer/v2",
    description:
      "Manages the search index. Allows reindexing records without re-ingesting via Storage API. Operates asynchronously — records are indexed after creation via Storage.",
    auth: "Bearer token. Header: data-partition-id (required).",
    endpoints: [
      {
        method: "POST",
        path: "/reindex",
        operationId: "reindex",
        summary: "Re-index all records of a specific kind.",
        roles: "service.search.admin",
      },
      {
        method: "PATCH",
        path: "/reindex",
        operationId: "fullReindex",
        summary: "Re-index entire data partition.",
        roles: "users.datalake.ops",
      },
      {
        method: "POST",
        path: "/reindex/records",
        operationId: "reindexRecords",
        summary: "Re-index specific records by id (up to 1000).",
      },
      {
        method: "DELETE",
        path: "/index",
        operationId: "deleteIndex",
        summary: "Delete index for a given kind.",
        params: ["kind (e.g. 'tenant1:public:well:1.0.2')"],
      },
    ],
  },

  notification: {
    title: "Notification Service",
    version: "1.0.0",
    basePath: "/api/notification/v1",
    description:
      "Pub/sub service for record change notifications. Works with Register service to enable consumers to subscribe to data changes.",
    endpoints: [
      {
        method: "POST",
        path: "/push-handlers/records-changed",
        operationId: "recordChanged",
        summary: "Notification handler for record change events.",
        roles: "users.datalake.ops or notification.pubsub",
      },
    ],
  },

  eds: {
    title: "External Data Sources Service",
    version: "2.0.0",
    basePath: "/api/eds/v1",
    description:
      "Manages retrieval of third-party datasets. Provides retrieval instructions for external data.",
    endpoints: [
      {
        method: "POST",
        path: "/retrievalInstructions",
        operationId: "getRetrievalInstructions",
        summary: "Get retrieval instructions for external datasets.",
        roles: "service.eds.user",
      },
    ],
  },
};

const INGESTION_GUIDE = {
  title: "OSDU/ADME Ingestion Best Practices",
  source: "https://github.com/microsoft/adme-samples/tree/main/rest-apis/M25",
  steps: [
    {
      step: 1,
      name: "Setup Legal Tags",
      description:
        "Create LegalTags before ingesting any data. Every record requires at least one valid LegalTag.",
      api: "POST /api/legal/v1/legaltags",
      example: {
        name: "{partition}-private-default",
        properties: {
          contractId: "No Contract Related",
          countryOfOrigin: ["US"],
          dataType: "Third Party Data",
          securityClassification: "Private",
          exportClassification: "EAR99",
          personalData: "No Personal Data",
        },
      },
    },
    {
      step: 2,
      name: "Verify Entitlements",
      description:
        "Ensure the service principal has appropriate data group memberships for ACL assignment.",
      api: "GET /api/entitlements/v2/groups",
      notes:
        "Records reference data groups in ACL. Common groups: data.default.owners@{partition}.dataservices.energy, data.default.viewers@{partition}.dataservices.energy",
    },
    {
      step: 3,
      name: "Check/Register Schema",
      description:
        "Verify the target schema exists. If ingesting custom data types, register the schema first.",
      api: "GET /api/schema-service/v1/schema?authority=osdu&source=wks&entityType={type}&status=PUBLISHED",
    },
    {
      step: 4,
      name: "Search Existing Records (Export)",
      description:
        "Use cursor-based search to export records from source ADME. Iterate until cursor is null.",
      api: "POST /api/search/v2/query_with_cursor",
      pattern: [
        "1. Initial request: { kind: 'osdu:wks:*:*', query: '...', limit: 1000 }",
        "2. Next pages: include cursor from previous response",
        "3. Continue until cursor is null or results empty",
        "4. Close cursor when done: DELETE /query_with_cursor/{cursor}",
      ],
    },
    {
      step: 5,
      name: "Transform Records for Target",
      description: "Remap record metadata for the target ADME instance.",
      transformations: [
        "Replace data-partition-id in record ids: source-partition:kind:id → target-partition:kind:id",
        "Update ACL groups to target partition's groups",
        "Update legal tags to target partition's legal tags",
        "Preserve or remap ancestry references",
        "Handle schema version differences between instances",
      ],
    },
    {
      step: 6,
      name: "Ingest Records (Import)",
      description:
        "Use Storage API PUT to create/update records in the target ADME. Process in batches of up to 500.",
      api: "PUT /api/storage/v2/records",
      notes: [
        "Batch size: up to 500 records per request",
        "Use skipdupes=true to avoid re-ingesting identical records",
        "Handle 429 rate limits with exponential backoff",
        "Track failed records from response (skippedRecordIds)",
        "Verify ingestion via Search API after indexer processes records",
      ],
    },
    {
      step: 7,
      name: "Upload Files (if applicable)",
      description: "For file-based records, upload the file content separately.",
      flow: [
        "1. GET /api/file/v2/files/uploadURL → SignedURL + FileSource",
        "2. PUT file bytes to the SignedURL",
        "3. POST /api/file/v2/files/metadata with FileSource in record body",
      ],
    },
  ],
  commonKinds: [
    "osdu:wks:master-data--Well:1.0.0",
    "osdu:wks:master-data--Wellbore:1.0.0",
    "osdu:wks:work-product-component--WellLog:1.4.0",
    "osdu:wks:work-product-component--WellboreTrajectory:1.1.0",
    "osdu:wks:work-product-component--SeismicHorizon:1.1.0",
    "osdu:wks:dataset--File.Generic:1.0.0",
    "osdu:wks:reference-data--UnitOfMeasure:1.0.0",
  ],
  errorHandling: {
    "400": "Bad request — check record structure, required fields, kind format",
    "401": "Token expired — refresh MSAL token",
    "403": "Missing permissions — check entitlements group membership",
    "404": "Record/schema not found — verify kind and id exist",
    "409": "Conflict — record version conflict during concurrent updates",
    "429": "Rate limited — implement exponential backoff, respect Retry-After header",
    "500": "Server error — retry with backoff",
    "502": "Bad gateway — service scaling, wait 10s and retry",
  },
};

const ALL_AVAILABLE_APIS = Object.keys(OSDU_APIS).join(", ");

const session = await joinSession({
  hooks: {
    onSessionStart: async () => {
      await session.log(
        "🔬 OSDU/ADME API Reference loaded (M25 release) — use the osdu_api_reference tool",
        { level: "info" }
      );
    },
  },
  tools: [
    {
      name: "osdu_api_reference",
      description: `Get OSDU/ADME API reference documentation for building integrations. Available services: ${ALL_AVAILABLE_APIS}. Use topic 'ingestion' for the end-to-end ingestion guide, 'overview' for a summary of all services, or a specific service name for detailed API docs.`,
      parameters: {
        type: "object",
        properties: {
          topic: {
            type: "string",
            description: `The API service or topic to look up. Options: ${ALL_AVAILABLE_APIS}, ingestion, overview, record-structure, auth, errors`,
          },
        },
        required: ["topic"],
      },
      handler: async (args) => {
        const topic = (args.topic || "").toLowerCase().trim();

        if (topic === "overview") {
          const summary = Object.entries(OSDU_APIS).map(([key, api]) => ({
            service: key,
            title: api.title,
            basePath: api.basePath,
            description: api.description,
            endpointCount: api.endpoints?.length || 0,
          }));
          return JSON.stringify(
            {
              title: "OSDU/ADME API Overview — M25 Release",
              source: "https://github.com/microsoft/adme-samples/tree/main/rest-apis/M25",
              services: summary,
              additionalSpecs: [
                "register — Register service (subscriptions, actions, DDMs)",
                "secret — Secret management service",
                "wellbore_ddms — Wellbore domain data management",
                "seismic_ddms — Seismic domain data management",
                "reservoir — Reservoir domain data management",
                "petrel_ddms — Petrel project data management",
                "crs_catalog — Coordinate reference system catalog",
                "crs_converter — Coordinate reference system conversion",
                "unit — Unit of measure service",
                "welldelivery_ddms — Well delivery domain data management",
                "rock_and_fluid_sample_ddms — Rock & fluid sample management",
                "seismic_file_metadata — Seismic file metadata management",
              ],
            },
            null,
            2
          );
        }

        if (topic === "ingestion") {
          return JSON.stringify(INGESTION_GUIDE, null, 2);
        }

        if (topic === "record-structure" || topic === "record") {
          return JSON.stringify(
            {
              title: "OSDU Record Structure",
              ...OSDU_APIS.storage.recordStructure,
              kindFormat: {
                pattern: "{authority}:{source}:{entity-type}:{version}",
                example: "osdu:wks:work-product-component--WellLog:1.4.0",
                segments: {
                  authority: "Schema authority (e.g. osdu)",
                  source: "Schema source (e.g. wks = well-known schema)",
                  entityType: "Entity type with optional group prefix (e.g. work-product-component--WellLog)",
                  version: "Semantic version (major.minor.patch)",
                },
              },
              idFormat: {
                pattern: "{data-partition-id}:{kind-sub-type}:{unique-id}",
                example: "opendes:work-product-component--WellLog:abc-123-def",
              },
            },
            null,
            2
          );
        }

        if (topic === "auth" || topic === "authentication") {
          return JSON.stringify(
            {
              title: "OSDU/ADME Authentication",
              method: "OAuth 2.0 Client Credentials flow via Azure AD / MSAL",
              headers: {
                Authorization: "Bearer {access_token}",
                "data-partition-id": "{partition-id} — identifies the data partition (tenant)",
                "Content-Type": "application/json",
              },
              tokenEndpoint: "https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token",
              scope: "{adme-client-id}/.default",
              notes: [
                "Use MSAL ConfidentialClientApplication for token acquisition",
                "Tokens are typically valid for 1 hour",
                "Refresh tokens 5 minutes before expiry",
                "Each ADME instance has its own client-id for scoping",
              ],
            },
            null,
            2
          );
        }

        if (topic === "errors" || topic === "error-handling") {
          return JSON.stringify(
            {
              title: "OSDU/ADME Error Handling Guide",
              errorCodes: INGESTION_GUIDE.errorHandling,
              retryStrategy: {
                description: "Exponential backoff with jitter",
                initialDelay: "1 second",
                maxDelay: "60 seconds",
                maxRetries: 5,
                retryOn: [429, 500, 502, 503],
                respectRetryAfter: "Always honor Retry-After header on 429 responses",
              },
              batchErrorHandling: [
                "Storage PUT /records may partially succeed — check skippedRecordIds in response",
                "Search query_with_cursor may return 502 during scale-up — wait 10s and retry",
                "Track failed record ids and retry them separately",
              ],
            },
            null,
            2
          );
        }

        if (OSDU_APIS[topic]) {
          return JSON.stringify(OSDU_APIS[topic], null, 2);
        }

        // Fuzzy match
        const match = Object.keys(OSDU_APIS).find(
          (k) => topic.includes(k) || k.includes(topic)
        );
        if (match) {
          return JSON.stringify(OSDU_APIS[match], null, 2);
        }

        return JSON.stringify({
          error: `Unknown topic: '${topic}'`,
          availableTopics: [
            ...Object.keys(OSDU_APIS),
            "ingestion",
            "overview",
            "record-structure",
            "auth",
            "errors",
          ],
          hint: "Use 'overview' for a summary of all services, or a specific service name for details.",
        });
      },
    },
  ],
});
