/**
 * Prometheus-style metrics module for OpsBob demo service
 * Exposes real process.memoryUsage() data and application metrics
 */

const os = require('os');

// Track application-level metrics
let requestCount = 0;
let errorCount = 0;
let lastRequestTimestamp = null;

/**
 * Increment request counter
 */
function trackRequest() {
  requestCount++;
  lastRequestTimestamp = Date.now();
}

/**
 * Increment error counter
 */
function trackError() {
  errorCount++;
}

/**
 * Get current metrics snapshot
 * @param {Map} sessionCache - Reference to the session cache for size tracking
 * @returns {object} Metrics object with memory and application stats
 */
function getMetrics(sessionCache) {
  const mem = process.memoryUsage();
  const cpuUsage = process.cpuUsage();

  return {
    // Memory metrics (in MB)
    heap_used_mb: Math.round(mem.heapUsed / 1024 / 1024 * 100) / 100,
    heap_total_mb: Math.round(mem.heapTotal / 1024 / 1024 * 100) / 100,
    rss_mb: Math.round(mem.rss / 1024 / 1024 * 100) / 100,
    external_mb: Math.round(mem.external / 1024 / 1024 * 100) / 100,

    // Raw memory (bytes)
    heap_used_bytes: mem.heapUsed,
    heap_total_bytes: mem.heapTotal,
    rss_bytes: mem.rss,

    // Application metrics
    cache_size: sessionCache ? sessionCache.size : 0,
    request_count: requestCount,
    error_count: errorCount,
    last_request: lastRequestTimestamp ? new Date(lastRequestTimestamp).toISOString() : null,

    // System metrics
    uptime_seconds: Math.round(process.uptime()),
    cpu_user_us: cpuUsage.user,
    cpu_system_us: cpuUsage.system,
    node_version: process.version,
    platform: os.platform(),
    total_memory_mb: Math.round(os.totalmem() / 1024 / 1024),
    free_memory_mb: Math.round(os.freemem() / 1024 / 1024),

    // Timestamp
    timestamp: new Date().toISOString(),
    collected_at: Date.now()
  };
}

/**
 * Get metrics in Prometheus text format
 * @param {Map} sessionCache
 * @returns {string}
 */
function getPrometheusMetrics(sessionCache) {
  const m = getMetrics(sessionCache);
  return [
    `# HELP nodejs_heap_used_bytes Node.js heap used in bytes`,
    `# TYPE nodejs_heap_used_bytes gauge`,
    `nodejs_heap_used_bytes ${m.heap_used_bytes}`,
    `# HELP nodejs_heap_total_bytes Node.js heap total in bytes`,
    `# TYPE nodejs_heap_total_bytes gauge`,
    `nodejs_heap_total_bytes ${m.heap_total_bytes}`,
    `# HELP nodejs_rss_bytes Node.js RSS in bytes`,
    `# TYPE nodejs_rss_bytes gauge`,
    `nodejs_rss_bytes ${m.rss_bytes}`,
    `# HELP app_cache_size Number of entries in session cache`,
    `# TYPE app_cache_size gauge`,
    `app_cache_size ${m.cache_size}`,
    `# HELP app_request_total Total requests processed`,
    `# TYPE app_request_total counter`,
    `app_request_total ${m.request_count}`,
    `# HELP app_error_total Total errors`,
    `# TYPE app_error_total counter`,
    `app_error_total ${m.error_count}`,
    `# HELP app_uptime_seconds Application uptime in seconds`,
    `# TYPE app_uptime_seconds gauge`,
    `app_uptime_seconds ${m.uptime_seconds}`,
  ].join('\n');
}

module.exports = { getMetrics, getPrometheusMetrics, trackRequest, trackError };
