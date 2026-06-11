const TARGET_DATABASE = "oracle_migration_hazem";

const elements = {
  oracleHealth: document.querySelector("#oracle-health"),
  clickhouseHealth: document.querySelector("#clickhouse-health"),
  sourceSchema: document.querySelector("#source-schema"),
  sourceTable: document.querySelector("#source-table"),
  partitionColumn: document.querySelector("#partition-column"),
  targetSchema: document.querySelector("#target-schema"),
  clickhouseDatabase: document.querySelector("#clickhouse-database"),
  targetTable: document.querySelector("#target-table"),
  workerThreads: document.querySelector("#worker-threads"),
  launchButton: document.querySelector("#launch-button"),
  launchMessage: document.querySelector("#launch-message"),
};

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

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail || data.error || data.message;
    const message = typeof detail === "string" ? detail : "Request failed";
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
    const data = await fetchJson(`/api/oracle/partition-columns?${query.toString()}`);
    const columns = (data.candidates || []).map((column) => ({
      value: column.column_name,
      label: `${column.column_name} (${column.data_type})`,
    }));
    setOptions(elements.partitionColumn, columns, "No partition/hash column");
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

function onLaunchClick() {
  const targetName = selectedTargetName();
  if (!targetName) {
    return;
  }

  const targetPath = `${TARGET_DATABASE}.${targetName}`;
  const confirmed = window.confirm(
    `Initial full load will drop and recreate ${targetPath}, then load the entire Oracle table. Continue?`,
  );

  elements.launchMessage.textContent = confirmed
    ? `Ready for Phase 6 wiring: ${targetPath} will be fully reloaded when migration logic is added.`
    : "Initial full load was not launched.";
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
