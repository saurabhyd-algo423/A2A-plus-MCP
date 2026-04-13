from typing import Dict, Any
import yfinance as yf

class YahooFinanceService:
    def __init__(self):
        """
        Initialises the Yahoo Finance service.
        """
        pass

    # def get_symbol_from_query(self, query: str) -> Dict[str, Any]:
    #     """
    #     Given a query (e.g. name of a company) returns a dictionary with info.
    #     Use only if you have no idea about the symbol.
    #     :param query: name of company
    #     :return: dictionary with the response to the query
    #     """
    #     data = yf.download(query, period='1d')
    #     if not data.empty:
    #         return {'symbol': query, 'name': data['Adj Close'].name}
    #     else:
    #         return None
    
    def get_stock_info(self, stock_symbol: str) -> Dict[str, Any]:
        """
        Fetches the stock information for the given stock symbol.
        :param stock_symbol: The stock symbol to fetch information for.
        :return: A dictionary containing the stock information.
        """
        try:
            # Create a Ticker object
            ticker = yf.Ticker(stock_symbol)
            # Get the live price and other info
            info = ticker.info

            # Return the values as a dictionary
            return {
                'current_price': info['currentPrice'],
                'change': info['regularMarketChange'],
                'percentage_change': info['regularMarketChangePercent'],
                'day_high': info['dayHigh'],
                'day_low': info['dayLow'],
                'day_open_price': info['open'],
                'previous_close_price': info['previousClose'],
            }
        except Exception as e:
            print(f"Error getting stock info for {stock_symbol} please use correct stock symbol.")
            return None

if __name__ == "__main__":
    service = YahooFinanceService()
    # Example usage
    # print(symbol_info)
    stock_symbol = 'TCS'  # Replace with the desired stock symbol
    # Get stock information
    stock_info = service.get_stock_info(stock_symbol)
    print(f"Stock information for {stock_symbol}:")
    print(stock_info)