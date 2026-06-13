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

function renderWorkers(workers) {
  const rows = Array.isArray(workers) ? workers : [];
  elements.workerProgressBody.replaceChildren();

  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 10;
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
    const values = [
      worker.worker_id,
      formatMode(worker.resolved_parallel_mode || worker.partition_mode),
      worker.partition_column || "-",
      rangeText,
      worker.status || "PENDING",
      formatNumber(worker.processed_rows),
      formatNumber(worker.inserted_rows),
      formatNumber(worker.batches_completed),
      formatNumber(worker.rows_per_second),
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

function setProgress(status) {
  const percent = Math.max(0, Math.min(100, Number(status.progress_percent || 0)));
  elements.progressPanel.hidden = false;
  elements.jobStatus.textContent = status.status || "PENDING";
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
  renderWorkers(status.workers);

  if (status.error_message) {
    elements.migrationError.hidden = false;
    elements.migrationError.textContent = status.error_message;
  } else {
    elements.migrationError.hidden = true;
    elements.migrationError.textContent = "";
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
