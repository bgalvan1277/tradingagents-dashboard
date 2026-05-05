-- Create trade_plans table for persisting day-trade briefings
CREATE TABLE IF NOT EXISTS trade_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker_symbol VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    confidence INT DEFAULT 0,
    thesis TEXT,
    plan_json JSON,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    tokens_used INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trade_plans_created (created_at),
    INDEX idx_trade_plans_ticker (ticker_symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
