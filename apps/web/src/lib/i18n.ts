export type Locale = "en" | "zh";

export interface Translations {
  appName: string; localMvp: string; workspaceTitle: string; workspaceDesc: string;
  noLiveTrading: string; priceBasedOnly: string; deterministicEngine: string;
  chatBuilderTitle: string; strategyParser: string; chatPlaceholder: string;
  chatSupported: string; interpret: string; interpreting: string;
  aiLabel: string; youLabel: string; chatWelcome: string;
  strategyDocTitle: string; markdownIntake: string; strategyDocDesc: string;
  uploadMd: string; strategyDocHint: string; parseMemo: string; parsingMemo: string;
  extractedFields: string; assumptions: string; ambiguities: string;
  validationTitle: string; needsAttention: string; readyToBacktest: string;
  clarificationPrompts: string; parserReady: string;
  strategyPreviewTitle: string; strategyPreviewDesc: string;
  runBacktest: string; runningBacktest: string;
  strategyName: string; benchmark: string; startDate: string; endDate: string;
  initialCapital: string; universe: string; transactionCost: string; slippage: string;
  strategyJson: string; sourceSummary: string; assumptionsTitle: string;
  ambiguitiesTitle: string; noAssumptions: string; noAmbiguities: string;
  extractionTrace: string; field: string; status: string; value: string; parseFirst: string;
  tabBacktest: string; tabExplanation: string; tabSandbox: string; tabComparison: string;
  totalReturn: string; sharpe: string; maxDrawdown: string; excessVsBenchmark: string;
  trades: string; equityCurve: string; metricsDetail: string; drawdownCurve: string;
  annualReturns: string; year: string; return: string; monthlyHeatmap: string;
  tradeLog: string; warningCount: string; symbol: string; entry: string; exit: string;
  holdDays: string; backtestEmpty: string; explanationEmpty: string;
  sandboxEmpty: string; trustScore: string; confidenceLevel: string;
  overfittingRisk: string; overfittingRiskLabel: string;
  benchmarkConcerns: string; regimeDependence: string; sensitivityConcerns: string;
  transactionCostConcerns: string; sampleSizeConcerns: string; dataQualityConcerns: string;
  reasonsToTrust: string; reasonsToDistrust: string;
  robustnessTests: string; suggestedNextTests: string;
  strengths: string; weaknesses: string; marketRegimeNotes: string; suggestedIterations: string;
  comparisonTitle: string; metric: string; current: string; previous: string; comparisonEmpty: string;
  errorInterpret: string; errorParseMemo: string; errorBacktest: string;
  searchPlaceholder: string; searching: string;
  maxSymbols: (n: number) => string;
  removeSymbol: (sym: string) => string;
  stale: (sym: string) => string;
  bars: (sym: string, n: number) => string;
  staleTitle: (n: number) => string;
  barsTitle: (n: number, date: string) => string;
  months: readonly string[];
  demoPrompts: readonly string[];
  // Robustness tab
  tabRobustness: string;
  runRobustness: string; runningRobustness: string;
  peerTickersPlaceholder: string; peerTickersLabel: string;
  robustnessSummary: string; robustnessEmpty: string; robustnessFailed: string;
  paramSensitivityTitle: string; subperiodTitle: string;
  txCostTitle: string; benchmarkCompTitle: string; peerTickerTitle: string;
  colParamSet: string; colPeriod: string; colCostBps: string;
  colTotalReturn: string; colSharpe: string; colMaxDrawdown: string;
  colTradeCount: string; colVerdict: string; colStart: string; colEnd: string;
  colAnnualReturn: string; colName: string; colExcess: string;
  colTicker: string; colTurnoverImpact: string;
  // Demo picker
  demosTitle: string; demosSubtitle: string;
  // Defaults callout
  defaultsTitle: string; defaultsNote: string; defaultBenchmark: string; defaultDates: string; defaultCosts: string;
  // Backtest disclaimer
  backtestDisclaimer: string;
}

const translations: Record<Locale, Translations> = {
  en: {
    // Header
    appName: "Livermore",
    localMvp: "Local MVP",
    workspaceTitle: "Research Workspace",
    workspaceDesc:
      "Turn a natural-language investment idea into validated strategy JSON, a deterministic backtest, and a skeptical sandbox review that pushes back on false confidence.",
    noLiveTrading: "No live trading",
    priceBasedOnly: "Price-based strategies only",
    deterministicEngine: "Deterministic backend engine",

    // Chat Builder
    chatBuilderTitle: "Chat Builder",
    strategyParser: "Strategy Parser",
    chatPlaceholder: "Describe a price-based strategy...",
    chatSupported: "Supported: moving averages, crossover, momentum, RSI, breakout, static allocation, commodity trend & rotation",
    interpret: "Interpret",
    interpreting: "Interpreting",
    aiLabel: "AI Builder",
    youLabel: "You",
    chatWelcome:
      "Describe a price-based investment rule and I'll turn it into structured strategy JSON, run a deterministic backtest, and then let a skeptical sandbox reviewer challenge the result.",

    // Strategy Doc
    strategyDocTitle: "Strategy Doc",
    markdownIntake: "Markdown Intake",
    strategyDocDesc:
      "Paste a research memo or upload a `.md` file. The parser will extract what is explicit and log every inferred default.",
    uploadMd: "Upload .md",
    strategyDocHint: "Best for real strategy memos that still map into the supported strategy families.",
    parseMemo: "Parse Memo",
    parsingMemo: "Parsing Memo",
    extractedFields: "extracted fields",
    assumptions: "assumptions",
    ambiguities: "ambiguities",

    // Validation State
    validationTitle: "Validation State",
    needsAttention: "Needs attention",
    readyToBacktest: "Ready to backtest",
    clarificationPrompts: "clarification prompt(s)",
    parserReady: "The parser has enough structure to produce a deterministic backtest request.",

    // Strategy Preview
    strategyPreviewTitle: "Strategy Preview",
    strategyPreviewDesc: "Confirm the parsed structure and adjust simple fields before the run.",
    runBacktest: "Run Backtest",
    runningBacktest: "Running Backtest",
    strategyName: "Strategy Name",
    benchmark: "Benchmark",
    startDate: "Start Date",
    endDate: "End Date",
    initialCapital: "Initial Capital",
    universe: "Universe",
    transactionCost: "Transaction Cost (bps)",
    slippage: "Slippage (bps)",
    strategyJson: "Structured Strategy JSON",
    sourceSummary: "Source Summary",
    assumptionsTitle: "Assumptions",
    ambiguitiesTitle: "Ambiguities",
    noAssumptions: "No inferred defaults were needed.",
    noAmbiguities: "No obvious ambiguity triggers were detected.",
    extractionTrace: "Extraction Trace",
    field: "Field",
    status: "Status",
    value: "Value",
    parseFirst: "Parse a strategy idea first to populate the preview and controls.",

    // Tabs
    tabBacktest: "Backtest",
    tabExplanation: "Explanation",
    tabSandbox: "Sandbox Review",
    tabComparison: "Comparison",

    // Backtest results
    totalReturn: "Total Return",
    sharpe: "Sharpe",
    maxDrawdown: "Max Drawdown",
    excessVsBenchmark: "Excess vs Benchmark",
    trades: "Trades",
    equityCurve: "Equity Curve",
    metricsDetail: "Metrics Detail",
    drawdownCurve: "Drawdown Curve",
    annualReturns: "Annual Returns",
    year: "Year",
    return: "Return",
    monthlyHeatmap: "Monthly Return Heatmap",
    tradeLog: "Trade Log",
    warningCount: "warning(s)",
    symbol: "Symbol",
    entry: "Entry",
    exit: "Exit",
    holdDays: "Hold Days",
    backtestEmpty: "Run a backtest to populate curves, metrics, annual returns, and the trade log.",

    // Explanation tab
    explanationEmpty: "The explainer populates after a successful backtest run.",

    // Sandbox tab
    sandboxEmpty:
      "The sandbox reviewer appears after the backtest so it can critique actual results instead of guessing.",
    trustScore: "Trust score:",
    confidenceLevel: "Confidence:",
    overfittingRisk: "Overfitting risk:",
    overfittingRiskLabel: "Overfitting Risk",
    benchmarkConcerns: "Benchmark Concerns",
    regimeDependence: "Regime Dependence",
    sensitivityConcerns: "Sensitivity Concerns",
    transactionCostConcerns: "Transaction Cost Concerns",
    sampleSizeConcerns: "Sample Size Concerns",
    dataQualityConcerns: "Data Quality Concerns",
    reasonsToTrust: "Reasons to Trust",
    reasonsToDistrust: "Reasons to Distrust",
    robustnessTests: "Required Next Tests",
    suggestedNextTests: "Suggested Experiments",

    // Explanation sections
    strengths: "Strengths",
    weaknesses: "Weaknesses",
    marketRegimeNotes: "Market Regime Notes",
    suggestedIterations: "Suggested Iterations",

    // Comparison tab
    comparisonTitle: "Current vs Previous Iteration",
    metric: "Metric",
    current: "Current",
    previous: "Previous",
    comparisonEmpty: "Re-run the strategy after a change to compare iterations side by side.",

    // Errors
    errorInterpret: "Could not interpret the strategy.",
    errorParseMemo: "Could not parse the markdown strategy memo.",
    errorBacktest: "Backtest run failed.",

    // Ticker search
    searchPlaceholder: "Search ticker or company name...",
    searching: "Searching…",
    maxSymbols: (n: number) => `Max ${n} symbols`,
    removeSymbol: (sym: string) => `Remove ${sym}`,

    // Data status badge
    stale: (sym: string) => `${sym} stale`,
    bars: (sym: string, n: number) => `${sym} ${n}d`,
    staleTitle: (n: number) => `${n} bars — stale or missing`,
    barsTitle: (n: number, date: string) => `${n} bars through ${date}`,

    // Month labels
    months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],

    // Demo prompts
    demoPrompts: [
      "Buy SPY when 50-day MA crosses above 200-day MA",
      "Buy GLD when price is above its 200-day moving average",
      "Rotate into top 2 commodities monthly from GLD, USO, UNG, DBA, SLV",
      "RSI mean reversion on AAPL: buy below 30, sell above 60",
    ],

    // Robustness tab
    tabRobustness: "Robustness",
    runRobustness: "Run Robustness Tests",
    runningRobustness: "Running Tests…",
    peerTickersLabel: "Peer Tickers (optional)",
    peerTickersPlaceholder: "e.g. MSFT, AMZN, TSLA",
    robustnessSummary: "Summary",
    robustnessEmpty: "Run robustness tests to stress-test the strategy across parameters, time periods, and cost assumptions.",
    robustnessFailed: "Robustness tests failed.",
    paramSensitivityTitle: "Parameter Sensitivity",
    subperiodTitle: "Sub-Period Performance",
    txCostTitle: "Transaction Cost Sensitivity",
    benchmarkCompTitle: "Benchmark Comparison",
    peerTickerTitle: "Peer Ticker Test",
    colParamSet: "Parameters", colPeriod: "Period", colCostBps: "Cost (bps)",
    colTotalReturn: "Total Return", colSharpe: "Sharpe", colMaxDrawdown: "Max DD",
    colTradeCount: "Trades", colVerdict: "Verdict", colStart: "Start", colEnd: "End",
    colAnnualReturn: "Ann. Return", colName: "Name", colExcess: "Excess vs Strategy",
    colTicker: "Ticker", colTurnoverImpact: "Turnover Impact",

    // Demo picker
    demosTitle: "Example Strategies",
    demosSubtitle: "Select an example to load a pre-built strategy, or describe your own in the chat below.",

    // Defaults callout
    defaultsTitle: "Review before running",
    defaultsNote: "Unspecified fields were filled with defaults. Confirm these match your intent.",
    defaultBenchmark: "Benchmark",
    defaultDates: "Date range",
    defaultCosts: "Transaction cost / slippage",

    // Backtest disclaimer
    backtestDisclaimer:
      "Backtest results are hypothetical. They assume perfect execution, no market impact, and historical data that may contain errors. Past performance does not predict future results. This tool is for research only — not financial advice.",
  },

  zh: {
    // Header
    appName: "谋士",
    localMvp: "本地测试版",
    workspaceTitle: "研究工作台",
    workspaceDesc:
      "将自然语言投资想法转化为量化策略 JSON，运行确定性回测，并通过沙盒评审员挑战结果中的虚假信心。",
    noLiveTrading: "仅限回测，无实盘交易",
    priceBasedOnly: "仅支持价格型策略",
    deterministicEngine: "确定性后端引擎",

    // Chat Builder
    chatBuilderTitle: "策略构建器",
    strategyParser: "策略解析器",
    chatPlaceholder: "描述一个基于价格的投资规则...",
    chatSupported: "支持：均线、交叉、动量、RSI、突破、静态配置、大宗商品趋势与轮动",
    interpret: "解析",
    interpreting: "解析中",
    aiLabel: "AI 助手",
    youLabel: "您",
    chatWelcome:
      "描述一个基于价格的投资规则，我将把它转化为结构化策略 JSON，运行确定性回测，并让沙盒评审员对结果进行挑战。",

    // Strategy Doc
    strategyDocTitle: "策略文档",
    markdownIntake: "Markdown 解析",
    strategyDocDesc:
      "粘贴研究备忘录或上传 .md 文件。解析器将提取明确信息并记录每个推断默认值。",
    uploadMd: "上传 .md",
    strategyDocHint: "适合已有研究备忘录且能映射到支持策略类型的场景。",
    parseMemo: "解析备忘录",
    parsingMemo: "解析中",
    extractedFields: "个提取字段",
    assumptions: "个假设",
    ambiguities: "个歧义",

    // Validation State
    validationTitle: "验证状态",
    needsAttention: "需要补充",
    readyToBacktest: "可以回测",
    clarificationPrompts: "个待确认问题",
    parserReady: "解析器已获取足够信息，可生成确定性回测请求。",

    // Strategy Preview
    strategyPreviewTitle: "策略预览",
    strategyPreviewDesc: "确认解析结构并在运行前调整字段。",
    runBacktest: "运行回测",
    runningBacktest: "回测中",
    strategyName: "策略名称",
    benchmark: "基准",
    startDate: "开始日期",
    endDate: "结束日期",
    initialCapital: "初始资金",
    universe: "标的池",
    transactionCost: "交易成本 (bps)",
    slippage: "滑点 (bps)",
    strategyJson: "结构化策略 JSON",
    sourceSummary: "来源摘要",
    assumptionsTitle: "假设",
    ambiguitiesTitle: "歧义",
    noAssumptions: "无推断默认值。",
    noAmbiguities: "未检测到明显歧义。",
    extractionTrace: "提取追踪",
    field: "字段",
    status: "状态",
    value: "值",
    parseFirst: "请先解析策略以填充预览和控制项。",

    // Tabs
    tabBacktest: "回测",
    tabExplanation: "解读",
    tabSandbox: "沙盒评审",
    tabComparison: "对比",

    // Backtest results
    totalReturn: "总收益",
    sharpe: "夏普比率",
    maxDrawdown: "最大回撤",
    excessVsBenchmark: "超额收益",
    trades: "交易次数",
    equityCurve: "净值曲线",
    metricsDetail: "详细指标",
    drawdownCurve: "回撤曲线",
    annualReturns: "年度收益",
    year: "年份",
    return: "收益率",
    monthlyHeatmap: "月度收益热力图",
    tradeLog: "交易记录",
    warningCount: "个警告",
    symbol: "标的",
    entry: "买入日",
    exit: "卖出日",
    holdDays: "持仓天数",
    backtestEmpty: "运行回测以填充曲线、指标、年度收益及交易记录。",

    // Explanation tab
    explanationEmpty: "策略解读将在回测成功后显示。",

    // Sandbox tab
    sandboxEmpty: "沙盒评审员将在回测完成后对实际结果进行评估，而非凭空猜测。",
    trustScore: "信任评分：",
    confidenceLevel: "置信度：",
    overfittingRisk: "过拟合风险：",
    overfittingRiskLabel: "过拟合风险",
    benchmarkConcerns: "基准问题",
    regimeDependence: "市场环境依赖",
    sensitivityConcerns: "参数敏感性问题",
    transactionCostConcerns: "交易成本问题",
    sampleSizeConcerns: "样本量问题",
    dataQualityConcerns: "数据质量问题",
    reasonsToTrust: "可信理由",
    reasonsToDistrust: "存疑理由",
    robustnessTests: "必要后续测试",
    suggestedNextTests: "建议实验方向",

    // Explanation sections
    strengths: "优势",
    weaknesses: "劣势",
    marketRegimeNotes: "市场环境备注",
    suggestedIterations: "建议迭代方向",

    // Comparison tab
    comparisonTitle: "当前与上次迭代对比",
    metric: "指标",
    current: "当前",
    previous: "上次",
    comparisonEmpty: "修改后重新运行策略以对比迭代结果。",

    // Errors
    errorInterpret: "无法解析该策略。",
    errorParseMemo: "无法解析 Markdown 策略备忘录。",
    errorBacktest: "回测运行失败。",

    // Ticker search
    searchPlaceholder: "搜索股票代码或公司名称...",
    searching: "搜索中…",
    maxSymbols: (n: number) => `最多 ${n} 个标的`,
    removeSymbol: (sym: string) => `删除 ${sym}`,

    // Data status badge
    stale: (sym: string) => `${sym} 数据陈旧`,
    bars: (sym: string, n: number) => `${sym} ${n}天`,
    staleTitle: (n: number) => `${n} 条数据 — 陈旧或缺失`,
    barsTitle: (n: number, date: string) => `${n} 条数据，截至 ${date}`,

    // Month labels
    months: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],

    // Demo prompts
    demoPrompts: [
      "当SPY的50日均线上穿200日均线时买入",
      "当GLD价格高于200日均线时买入黄金ETF",
      "每月从GLD、USO、UNG、DBA、SLV中轮动买入动量最强的2只",
      "AAPL的RSI均值回归：RSI低于30时买入，高于60时卖出",
    ],

    // Robustness tab
    tabRobustness: "稳健性测试",
    runRobustness: "运行稳健性测试",
    runningRobustness: "测试运行中…",
    peerTickersLabel: "同类标的（可选）",
    peerTickersPlaceholder: "例如 MSFT, AMZN, TSLA",
    robustnessSummary: "测试摘要",
    robustnessEmpty: "运行稳健性测试，对策略的参数、时间段及成本假设进行压力测试。",
    robustnessFailed: "稳健性测试失败。",
    paramSensitivityTitle: "参数敏感性",
    subperiodTitle: "子区间表现",
    txCostTitle: "交易成本敏感性",
    benchmarkCompTitle: "基准对比",
    peerTickerTitle: "同类标的测试",
    colParamSet: "参数", colPeriod: "区间", colCostBps: "成本 (bps)",
    colTotalReturn: "总收益", colSharpe: "夏普", colMaxDrawdown: "最大回撤",
    colTradeCount: "交易次数", colVerdict: "结论", colStart: "开始", colEnd: "结束",
    colAnnualReturn: "年化收益", colName: "名称", colExcess: "相对策略超额",
    colTicker: "标的", colTurnoverImpact: "换手影响",

    // Demo picker
    demosTitle: "示例策略",
    demosSubtitle: "选择示例以加载预设策略，或在下方对话框中描述你自己的想法。",

    // Defaults callout
    defaultsTitle: "运行前请确认",
    defaultsNote: "未指定的字段已填入默认值，请确认这些设置符合您的意图。",
    defaultBenchmark: "基准",
    defaultDates: "日期范围",
    defaultCosts: "交易成本 / 滑点",

    // Backtest disclaimer
    backtestDisclaimer:
      "回测结果为假设性数据，假设完美执行、无市场冲击，且历史数据可能存在误差。历史表现不代表未来结果。本工具仅供研究使用，不构成投资建议。",
  },
};

export { translations };
