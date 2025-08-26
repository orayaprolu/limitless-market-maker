import numpy as np
from scipy.stats import norm

def binary_option_price(S, X, T, r, sigma, option_type='call'):
    d1 = (np.log(S / X) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        price = np.exp(-r * T) * norm.cdf(d2)
    else:  # put option
        price = np.exp(-r * T) * norm.cdf(-d2)

    return price

# if __name__ == "__main__":
#     # Example parameters
#     S = 100      # Underlying asset price
#     X = 100      # Strike price
#     T = 1        # Time to expiration in years
#     r = 0.05     # Risk-free interest rate
#     sigma = 0.2  # Implied volatility

#     # Calculate binary call and put prices
#     binary_call_price = binary_option_price(S, X, T, r, sigma, 'call')
#     binary_put_price = binary_option_price(S, X, T, r, sigma, 'put')

#     print(f'Binary Call Option Price: {binary_call_price}')
#     print(f'Binary Put Option Price: {binary_put_price}')
