const TARGET_DATABASE = "oracle_migration_hazem";

const elements = {
  oracleHealth: document.querySelector("#oracle-health"),
  clickhouseHealth: document.querySelector("#clickhouse-health"),
  sourceSchema: document.querySelector("#source-schema"),
  sourceTable: document.querySelector("#source-table"),
  partitionColumn: document.querySelector("#partition-column"),
  parallelMode: document.querySelector("#parallel-mode"),
  targetSchema: document.querySelector("#target-schema"),
  clickhouseDatabase: document.querySelector("#clickhouse-database"),
  targetTable: document.querySelector("#target-table"),
  workerThreads: document.querySelector("#worker-threads"),
  launchButton: document.querySelector("#launch-button"),
  launchMessage: document.querySelector("#launch-message"),
  progressPanel: document.querySelector("#migration-progress"),
  jobIdText: document.querySelector("#job-id-text"),
  jobStatus: document.querySelector("#job-status"),
  progressFill: document.querySelector("#progress-fill"),
  progressPercent: document.querySelector("#progress-percent"),
  totalRows: document.querySelector("#total-rows"),
  processedRows: document.querySelector("#processed-rows"),
  insertedRows: document.querySelector("#inserted-rows"),
  remainingRows: document.querySelector("#remaining-rows"),
  elapsedSeconds: document.querySelector("#elapsed-seconds"),
  rowsPerSecond: document.querySelector("#rows-per-second"),
  currentBatch: document.querySelector("#current-batch"),
  requestedParallelMode: document.querySelector("#requested-parallel-mode"),
  resolvedParallelMode: document.querySelector("#resolved-parallel-mode"),
  migrationError: document.querySelector("#migration-error"),
  timeoutActions: document.querySelector("#timeout-actions"),
  tuningInsertBatchSize: document.querySelector("#tuning-insert-batch-size"),
  tuningMaxConcurrentInserts: document.querySelector("#tuning-max-concurrent-inserts"),
  tuningInsertWait: document.querySelector("#tuning-insert-wait"),
  tuningTimeoutCount: document.querySelector("#tuning-timeout-count"),
  tuningErrorCount: document.querySelector("#tuning-error-count"),
  tuningRetryCount: document.querySelector("#tuning-retry-count"),
  tuningValidationMode: document.querySelector("#tuning-validation-mode"),
  tuningValidationTimeout: document.querySelector("#tuning-validation-timeout"),
  tuningDynamicChunks: document.querySelector("#tuning-dynamic-chunks"),
  tuningChunkCount: document.querySelector("#tuning-chunk-count"),
  tuningCompletedChunks: document.querySelector("#tuning-completed-chunks"),
  tuningFailedChunks: document.querySelector("#tuning-failed-chunks"),
  tuningRecommendations: document.querySelector("#tuning-recommendations"),
  diagnosticsSemantics: document.querySelector("#diagnostics-semantics"),
  diagTotalDuration: document.querySelector("#diag-total-duration"),
  diagOracleCount: document.querySelector("#diag-oracle-count"),
  diagOracleConnect: document.querySelector("#diag-oracle-connect"),
  diagOracleExecute: document.querySelector("#diag-oracle-execute"),
  diagOracleFetch: document.querySelector("#diag-oracle-fetch"),
  diagRowConversion: document.querySelector("#diag-row-conversion"),
  diagClickhouseConnect: document.querySelector("#diag-clickhouse-connect"),
  diagClickhouseInsert: document.querySelector("#diag-clickhouse-insert"),
  diagValidation: document.querySelector("#diag-validation"),
  diagBatchSize: document.querySelector("#diag-batch-size"),
  diagAverageRows: document.querySelector("#diag-average-rows"),
  diagAverageSeconds: document.querySelector("#diag-average-seconds"),
  diagMaxWorkerFetch: document.querySelector("#diag-max-worker-fetch"),
  diagMaxWorkerConvert: document.querySelector("#diag-max-worker-convert"),
  diagMaxWorkerInsert: document.querySelector("#diag-max-worker-insert"),
  diagnosticsWarnings: document.querySelector("#diagnostics-warnings"),
  validationSummary: document.querySelector("#validation-summary"),
  sourceRowCount: document.querySelector("#source-row-count"),
  targetRowCount: document.querySelector("#target-row-count"),
  countMatch: document.querySelector("#count-match"),
  validationStatus: document.querySelector("#validation-status"),
  validationError: document.querySelector("#validation-error"),
  workerProgressBody: document.querySelector("#worker-progress-body"),
};

let activePollTimer = null;

function setOptions(select, options, placeholder) {
  select.replaceChildren();

  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = placeholder;
  select.appendChild(placeholderOption);

  for (const option of options) {
    const item = document.createElement("option");
    item.value = option.value;
    item.textContent = option.label;
    select.appendChild(item);
  }
}

function safeErrorMessage(error) {
  if (error && typeof error.message === "string") {
    return error.message;
  }
  return "Request failed";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail || data.error || data.message;
    const message = typeof detail === "string" ? detail : detail?.error || "Request failed";
    throw new Error(message);
  }

  return data;
}

function setHealth(card, state, message) {
  const text = card.querySelector("[data-status-text]");
  card.dataset.state = state;
  text.textContent = message;
}

async function loadHealth() {
  try {
    const oracle = await fetchJson("/api/health/oracle");
    setHealth(
      elements.oracleHealth,
      oracle.status === "success" ? "success" : "error",
      oracle.status === "success" ? "Connected and metadata-readable" : "Oracle health check failed",
    );
  } catch (error) {
    setHealth(elements.oracleHealth, "error", safeErrorMessage(error));
  }

  try {
    const clickhouse = await fetchJson("/api/health/clickhouse");
    const exists = clickhouse.target_database_exists ? "exists" : "does not exist";
    setHealth(
      elements.clickhouseHealth,
      clickhouse.status === "success" ? "success" : "warning",
      `Target database ${TARGET_DATABASE} ${exists}`,
    );
  } catch (error) {
    setHealth(elements.clickhouseHealth, "error", safeErrorMessage(error));
  }
}

async function loadSchemas() {
  elements.sourceSchema.disabled = true;
  setOptions(elements.sourceSchema, [], "Loading schemas...");

  try {
    const data = await fetchJson("/api/oracle/schemas");
    const schemas = (data.schemas || []).map((schema) => ({ value: schema, label: schema }));
    setOptions(elements.sourceSchema, schemas, "Select a schema");
    elements.sourceSchema.disabled = false;
  } catch (error) {
    setOptions(elements.sourceSchema, [], safeErrorMessage(error));
  }
}

async function loadTables(schema) {
  elements.sourceTable.disabled = true;
  elements.partitionColumn.disabled = true;
  elements.targetTable.value = "";
  setOptions(elements.sourceTable, [], "Loading tables...");
  setOptions(elements.partitionColumn, [], "Select a table first");
  updateLaunchState();

  if (!schema) {
    setOptions(elements.sourceTable, [], "Select a schema first");
    return;
  }

  try {
    const data = await fetchJson(`/api/oracle/tables?schema=${encodeURIComponent(schema)}`);
    const tables = (data.tables || []).map((table) => ({ value: table, label: table }));
    setOptions(elements.sourceTable, tables, "Select a table");
    elements.sourceTable.disabled = false;
  } catch (error) {
    setOptions(elements.sourceTable, [], safeErrorMessage(error));
  }
}

async function loadPartitionColumns(schema, table) {
  elements.partitionColumn.disabled = true;
  setOptions(elements.partitionColumn, [], "Loading columns...");
  updateLaunchState();

  if (!schema || !table) {
    setOptions(elements.partitionColumn, [], "Select a table first");
    return;
  }

  try {
    const query = new URLSearchParams({ schema, table });
    const data = await fetchJson(`/api/oracle/columns?${query.toString()}`);
    const columns = (data.columns || []).map((column) => ({
      value: column.column_name,
      label: `${column.column_name} (${column.data_type})`,
    }));
    setOptions(elements.partitionColumn, columns, "Select a partition/hash column");
    elements.partitionColumn.disabled = false;
  } catch (error) {
    setOptions(elements.partitionColumn, [], safeErrorMessage(error));
  }
}

function selectedTargetName() {
  const targetSchema = elements.targetSchema.value.trim();
  const targetTable = elements.targetTable.value.trim();

  if (!targetSchema || !targetTable) {
    return "";
  }

  return `${targetSchema}__${targetTable}`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatMode(value) {
  return String(value || "pending").replaceAll("_", " ");
}

function formatSeconds(value) {
  return `${Number(value || 0).toFixed(3)}s`;
}

function formatOptionalNumber(value) {
  return value === null || value === undefined ? "-" : formatNumber(value);
}

function formatCountMatch(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return value ? "Yes" : "No";
}

function rowCountDifference(status) {
  const sourceCount = Number(status.source_row_count || 0);
  const targetCount = Number(status.target_row_count || 0);
  return Math.abs(sourceCount - targetCount);
}

function renderWorkers(workers) {
  const rows = Array.isArray(workers) ? workers : [];
  elements.workerProgressBody.replaceChildren();

  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 14;
    cell.textContent = "No worker progress yet.";
    row.appendChild(cell);
    elements.workerProgressBody.appendChild(row);
    return;
  }

  for (const worker of rows) {
    const row = document.createElement("tr");
    const rangeText = worker.range_start === null && worker.range_end === null
      ? "hash bucket"
      : `${worker.range_start ?? ""} to ${worker.range_end ?? ""}`;
    const timings = worker.timings || {};
    const values = [
      worker.worker_id,
      worker.current_chunk_id ?? "-",
      formatMode(worker.resolved_parallel_mode || worker.partition_mode),
      worker.partition_column || "-",
      rangeText,
      worker.status || "PENDING",
      formatNumber(worker.processed_rows),
      formatNumber(worker.inserted_rows),
      formatNumber(worker.batches_completed),
      formatNumber(worker.rows_per_second),
      formatSeconds(timings.oracle_fetch_duration_seconds),
      formatSeconds(timings.row_conversion_duration_seconds),
      formatSeconds(timings.clickhouse_insert_duration_seconds),
      worker.error_message || "",
    ];

    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    elements.workerProgressBody.appendChild(row);
  }
}

function renderList(element, items, emptyText) {
  element.replaceChildren();
  if (!items.length) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    element.appendChild(item);
    return;
  }
  for (const text of items) {
    const item = document.createElement("li");
    item.textContent = text;
    element.appendChild(item);
  }
}

function renderInsertTuning(status) {
  const diagnostics = status.performance_diagnostics || {};
  elements.tuningInsertBatchSize.textContent = formatNumber(
    status.clickhouse_insert_batch_size || diagnostics.clickhouse_insert_batch_size,
  );
  elements.tuningMaxConcurrentInserts.textContent = formatNumber(
    status.max_concurrent_clickhouse_inserts || diagnostics.max_concurrent_clickhouse_inserts,
  );
  elements.tuningInsertWait.textContent = formatSeconds(
    status.insert_wait_seconds || diagnostics.insert_wait_seconds,
  );
  elements.tuningTimeoutCount.textContent = formatNumber(
    status.clickhouse_insert_timeout_count || diagnostics.clickhouse_insert_timeout_count,
  );
  elements.tuningErrorCount.textContent = formatNumber(
    status.clickhouse_insert_error_count || diagnostics.clickhouse_insert_error_count,
  );
  elements.tuningRetryCount.textContent = formatNumber(
    status.clickhouse_insert_retries || diagnostics.clickhouse_insert_retries,
  );
  elements.tuningValidationMode.textContent = status.validation_mode || diagnostics.validation_mode || "fast";
  elements.tuningValidationTimeout.textContent = formatSeconds(
    status.validation_timeout_seconds || diagnostics.validation_timeout_seconds,
  );
  elements.tuningDynamicChunks.textContent = status.dynamic_chunks_enabled ? "true" : "false";
  elements.tuningChunkCount.textContent = formatNumber(status.chunk_count);
  elements.tuningCompletedChunks.textContent = formatNumber(status.completed_chunk_count);
  elements.tuningFailedChunks.textContent = formatNumber(status.failed_chunk_count);
  renderList(
    elements.tuningRecommendations,
    Array.isArray(status.recommendations) ? status.recommendations : [],
    "No recommendations yet.",
  );
}

function renderDiagnostics(status) {
  const diagnostics = status.performance_diagnostics || {};
  const workerSummary = diagnostics.per_worker_summary || {};
  if (diagnostics.timing_semantics === "cumulative_worker_seconds") {
    elements.diagnosticsSemantics.textContent = "Parallel aggregate timing fields are cumulative worker-seconds; max worker timings show the wall-clock bottleneck.";
  } else {
    elements.diagnosticsSemantics.textContent = "Timing fields are wall-clock seconds for the single load path.";
  }
  elements.diagTotalDuration.textContent = formatSeconds(diagnostics.total_duration_seconds);
  elements.diagOracleCount.textContent = formatSeconds(diagnostics.oracle_count_duration_seconds);
  elements.diagOracleConnect.textContent = formatSeconds(diagnostics.oracle_connect_duration_seconds);
  elements.diagOracleExecute.textContent = formatSeconds(diagnostics.oracle_execute_duration_seconds);
  elements.diagOracleFetch.textContent = formatSeconds(diagnostics.oracle_fetch_duration_seconds);
  elements.diagRowConversion.textContent = formatSeconds(diagnostics.row_conversion_duration_seconds);
  elements.diagClickhouseConnect.textContent = formatSeconds(diagnostics.clickhouse_connect_duration_seconds);
  elements.diagClickhouseInsert.textContent = formatSeconds(diagnostics.clickhouse_insert_duration_seconds);
  elements.diagValidation.textContent = formatSeconds(diagnostics.validation_duration_seconds);
  elements.diagBatchSize.textContent = formatNumber(diagnostics.batch_size);
  elements.diagAverageRows.textContent = formatNumber(diagnostics.average_rows_per_batch);
  elements.diagAverageSeconds.textContent = formatSeconds(diagnostics.average_seconds_per_batch);
  elements.diagMaxWorkerFetch.textContent = formatSeconds(workerSummary.oracle_fetch_duration_seconds?.max);
  elements.diagMaxWorkerConvert.textContent = formatSeconds(workerSummary.row_conversion_duration_seconds?.max);
  elements.diagMaxWorkerInsert.textContent = formatSeconds(workerSummary.clickhouse_insert_duration_seconds?.max);

  const warnings = Array.isArray(status.warnings) ? status.warnings : [];
  renderList(elements.diagnosticsWarnings, warnings, "No warnings.");
}

function renderValidation(status) {
  const validationStatus = status.validation_status || "NOT_STARTED";
  elements.validationStatus.textContent = validationStatus;
  elements.sourceRowCount.textContent = formatOptionalNumber(status.source_row_count);
  elements.targetRowCount.textContent = formatOptionalNumber(status.target_row_count);
  elements.countMatch.textContent = formatCountMatch(status.count_match);

  elements.validationError.hidden = true;
  elements.validationError.textContent = "";

  if (validationStatus === "RUNNING") {
    elements.validationSummary.textContent = "Validation running...";
    return;
  }

  if (validationStatus === "SUCCESS") {
    elements.validationSummary.textContent = "Validation succeeded: Oracle and ClickHouse row counts match.";
    return;
  }

  if (validationStatus === "FAILED") {
    const difference = rowCountDifference(status);
    elements.validationSummary.textContent = `Validation failed. Row count difference: ${formatNumber(difference)}.`;
    if (status.validation_error_message) {
      elements.validationError.hidden = false;
      elements.validationError.textContent = status.validation_error_message;
    }
    return;
  }

  if (validationStatus === "SKIPPED") {
    elements.validationSummary.textContent = "Validation skipped by configuration.";
    if (status.validation_error_message) {
      elements.validationError.hidden = false;
      elements.validationError.textContent = status.validation_error_message;
    }
    return;
  }

  if (validationStatus === "TIMEOUT") {
    elements.validationSummary.textContent = "Validation timed out after the data load completed.";
    if (status.validation_error_message) {
      elements.validationError.hidden = false;
      elements.validationError.textContent = status.validation_error_message;
    }
    return;
  }

  elements.validationSummary.textContent = "Validation has not started.";
}

function setProgress(status) {
  const percent = Math.max(0, Math.min(100, Number(status.progress_percent || 0)));
  elements.progressPanel.hidden = false;
  const validationStatus = status.validation_status || "NOT_STARTED";
  elements.jobStatus.textContent =
    status.status === "SUCCESS" && ["FAILED", "TIMEOUT", "SKIPPED"].includes(validationStatus)
      ? `SUCCESS (${validationStatus})`
      : status.status || "PENDING";
  elements.progressFill.style.width = `${percent}%`;
  elements.progressPercent.textContent = `${percent.toFixed(1)}%`;
  elements.totalRows.textContent = formatNumber(status.total_rows);
  elements.processedRows.textContent = formatNumber(status.processed_rows);
  elements.insertedRows.textContent = formatNumber(status.inserted_rows);
  elements.remainingRows.textContent = formatNumber(status.remaining_rows);
  elements.elapsedSeconds.textContent = `${Number(status.elapsed_seconds || 0).toFixed(1)}s`;
  elements.rowsPerSecond.textContent = formatNumber(status.rows_per_second);
  elements.currentBatch.textContent = formatNumber(
    status.current_batch_number || status.current_batch,
  );
  elements.requestedParallelMode.textContent = formatMode(status.requested_parallel_mode);
  elements.resolvedParallelMode.textContent = formatMode(status.resolved_parallel_mode);
  renderDiagnostics(status);
  renderInsertTuning(status);
  renderValidation(status);
  renderWorkers(status.workers);

  if (status.error_message) {
    elements.migrationError.hidden = false;
    elements.migrationError.textContent = status.error_message;
    elements.timeoutActions.hidden = !String(status.error_message).includes("ClickHouse insert timed out");
  } else {
    elements.migrationError.hidden = true;
    elements.migrationError.textContent = "";
    elements.timeoutActions.hidden = true;
  }
}

function stopPolling() {
  if (activePollTimer) {
    window.clearInterval(activePollTimer);
    activePollTimer = null;
  }
}

async function pollStatus(jobId) {
  try {
    const status = await fetchJson(`/api/migrations/${encodeURIComponent(jobId)}/status`);
    setProgress(status);

    if (["SUCCESS", "FAILED", "CANCELLED"].includes(status.status)) {
      stopPolling();
      elements.launchButton.disabled = false;
    }
  } catch (error) {
    stopPolling();
    elements.launchButton.disabled = false;
    elements.launchMessage.textContent = safeErrorMessage(error);
  }
}

function startPolling(jobId) {
  stopPolling();
  pollStatus(jobId);
  activePollTimer = window.setInterval(() => pollStatus(jobId), 2000);
}

function updateLaunchState() {
  const canLaunch = Boolean(
    elements.sourceSchema.value &&
      elements.sourceTable.value &&
      elements.targetTable.value.trim(),
  );
  elements.launchButton.disabled = !canLaunch;
}

function resetLaunchMessage() {
  elements.launchMessage.textContent = "";
}

function onSchemaChange() {
  const schema = elements.sourceSchema.value;
  elements.targetSchema.value = schema;
  resetLaunchMessage();
  loadTables(schema);
}

function onTableChange() {
  const schema = elements.sourceSchema.value;
  const table = elements.sourceTable.value;
  elements.targetTable.value = table;
  resetLaunchMessage();
  loadPartitionColumns(schema, table);
  updateLaunchState();
}

async function onLaunchClick() {
  const targetName = selectedTargetName();
  if (!targetName) {
    return;
  }

  const targetPath = `${TARGET_DATABASE}.${targetName}`;
  const confirmed = window.confirm(
    `Initial full load will drop and recreate ${targetPath}, then load the entire Oracle table. Continue?`,
  );

  if (!confirmed) {
    elements.launchMessage.textContent = "Initial full load was not launched.";
    return;
  }

  const payload = {
    source_schema: elements.sourceSchema.value,
    source_table: elements.sourceTable.value,
    target_schema: elements.targetSchema.value.trim() || null,
    target_database: TARGET_DATABASE,
    target_table: elements.targetTable.value.trim(),
    partition_column: elements.partitionColumn.value || null,
    parallel_mode: elements.parallelMode.value || "auto",
    workers: Number(elements.workerThreads.value || 1),
  };

  try {
    elements.launchButton.disabled = true;
    elements.launchMessage.textContent = `Launching full load for ${targetPath}...`;
    elements.progressPanel.hidden = false;
    elements.jobIdText.textContent = "Creating migration job...";
    elements.migrationError.hidden = true;

    const response = await fetchJson("/api/migrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    elements.jobIdText.textContent = `Job ${response.job_id}`;
    elements.requestedParallelMode.textContent = formatMode(response.requested_parallel_mode);
    elements.resolvedParallelMode.textContent = formatMode(response.resolved_parallel_mode);
    elements.launchMessage.textContent = `Migration job ${response.job_id} started. Polling live status.`;
    if (response.warning_message) {
      elements.launchMessage.textContent += ` ${response.warning_message}`;
    }
    startPolling(response.job_id);
  } catch (error) {
    elements.launchButton.disabled = false;
    elements.launchMessage.textContent = safeErrorMessage(error);
  }
}

function bindEvents() {
  elements.sourceSchema.addEventListener("change", onSchemaChange);
  elements.sourceTable.addEventListener("change", onTableChange);
  elements.targetSchema.addEventListener("input", updateLaunchState);
  elements.targetTable.addEventListener("input", updateLaunchState);
  elements.launchButton.addEventListener("click", onLaunchClick);
}

function init() {
  elements.clickhouseDatabase.value = TARGET_DATABASE;
  elements.clickhouseDatabase.disabled = true;
  bindEvents();
  updateLaunchState();
  loadHealth();
  loadSchemas();
}

document.addEventListener("DOMContentLoaded", init);
