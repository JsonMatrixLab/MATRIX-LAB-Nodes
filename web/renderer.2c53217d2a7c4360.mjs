export function isVueNodesMode(host = globalThis) {
  const liteGraph = host?.LiteGraph;
  if (liteGraph != null) return liteGraph.vueNodesMode === true;
  return host?.__MATRIX_TEST_VUE_NODES_MODE__ === true;
}
