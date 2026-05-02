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
  sandboxEmpty: string; trustScore: string;
  benchmarkConcerns: string; regimeDependence: string; sensitivityConcerns: string;
  transactionCostConcerns: string; sampleSizeConcerns: string;
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
}

const translations: Record<Locale, Translations> = {
  en: {
    // Header
    appName: "StrategyLab AI",
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
    chatSupported: "Supported: moving averages, crossover, momentum, RSI, breakout, static allocation",
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
    benchmarkConcerns: "Benchmark Concerns",
    regimeDependence: "Regime Dependence",
    sensitivityConcerns: "Sensitivity Concerns",
    transactionCostConcerns: "Transaction Cost Concerns",
    sampleSizeConcerns: "Sample Size Concerns",
    robustnessTests: "Required Robustness Tests",
    suggestedNextTests: "Suggested Next Tests",

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
      "Rotate into top 3 momentum stocks monthly from QQQ, IWM, EEM",
      "RSI mean reversion on AAPL: buy below 30, sell above 60",
      "60% SPY / 40% TLT rebalanced monthly",
    ],
  },

  zh: {
    // Header
    appName: "StrategyLab AI",
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
    chatSupported: "支持：均线、交叉、动量、RSI、突破、静态配置",
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
    benchmarkConcerns: "基准问题",
    regimeDependence: "市场环境依赖",
    sensitivityConcerns: "参数敏感性问题",
    transactionCostConcerns: "交易成本问题",
    sampleSizeConcerns: "样本量问题",
    robustnessTests: "需要的稳健性测试",
    suggestedNextTests: "建议后续测试",

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
      "每月从QQQ、IWM、EEM中轮动买入动量最强的3只",
      "AAPL的RSI均值回归：RSI低于30时买入，高于60时卖出",
      "60% SPY / 40% TLT 每月再平衡",
    ],
  },
};

export { translations };
