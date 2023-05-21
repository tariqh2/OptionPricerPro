from django.db import models

import pandas as pd
import math
import scipy.stats as si
from datetime import datetime, timedelta
from pandas.tseries.offsets import CustomBusinessDay
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import BDay


"""
    Seperate models for ProductName and DeliveryMonth are set up to allow unique values in the form dropdown.
    This is because we want to stick with the SQLite database before switching to PostgreSQL
    We want unique values for ProductName and DeliveryMonth in the dropdown but SQLite does not support
    ordered querysets.
    So we create two models for ProductName and DeliveryMonth that contain a set of unique values of each from MarketData
    These update automatically whenever the MarketData model is updated.

"""

class ProductName(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

class DeliveryMonth(models.Model):
    month = models.DateField(unique=True) 

    def __str__(self):
        return self.month.strftime('%Y-%m')


class MarketData(models.Model):
    """
    This model represents the daily settlement data for the underlying futures contracts. 

    Fields:
    settlement_date: The date on which the futures price settled.
    product_name: The underyling commodity of futures contract, e.g. WTI Crude,Henry Hub, etc.
    delivery_month: The contract month for delivery. 
    futures_price: The settlement price of the futures contract for a particular date.

    """
    settlement_date = models.DateField()
    product_name = models.CharField(max_length=200)
    delivery_month = models.DateField()  
    futures_price = models.DecimalField(max_digits=10, decimal_places=2) 

    def __str__(self):
        return f"{self.settlement_date} {self.product_name} {self.delivery_month}"

class USTreasuryYields(models.Model):
    """
    This model represents the market data for U.S. Treasury yields, 
    specifically the 2-year yield, which is considered a 'risk-free' rate. 

    Fields:
    date: The date of the yield rate.
    yield_rate: The yield rate of the U.S. Treasury note.
    """
    date = models.DateField()
    yield_rate = models.DecimalField(max_digits=5, decimal_places=2) 

    def __str__(self):
        return f"{self.date} - {self.yield_rate}%"
    

class Option(models.Model):
    """
    This model represents the options which price will be calculated.
    Assume this option will be a 'European' style option

    Fields:
    option_type: The type of options contract, either 'Call' or 'Put'.
    underlying_future: The underlying futures contract for the option. 
                      This is a foreign key relationship to the ProductName model.
    delivery_month: The delivery month for the option. 
                    This is also a foreign key relationship to the DeliveryMonth model.
    strike_price: The strike price of the option.

    Methods:
    expiry_date: A property that calculates the expiry date of the option.
    calculate_option_price: A method that calculates the price of the option using the Black76 formula.
    """
    OPTION_TYPE_CHOICES = [
        ('CALL', 'Call'),
        ('PUT', 'Put'),
    ]

    option_type = models.CharField(max_length=4, choices=OPTION_TYPE_CHOICES)
    underlying_future = models.ForeignKey(ProductName, on_delete=models.CASCADE, related_name="underlying")
    delivery_month = models.ForeignKey(DeliveryMonth, on_delete=models.CASCADE, related_name="delivery") 
    strike_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Creating an instance of the custom business day class using the US Federal Holiday calendar.
    # CustomBusinessDay is a class in pandas which considers custom business days, in this case, excluding US Federal holidays.
    us_bd = CustomBusinessDay(calendar=USFederalHolidayCalendar())

    def calculate_oil_expiry(self):
        """
        Calculates the expiry date for a Crude Oil future.
        The expiration date is the third business day prior to the 25th day of the month preceding the delivery month.
        Due to the expiry date being on the 25th of the preceding month of delivery we have to account for when the delivery
        month is January meaning we need to look at the December in the previous year. 
        A wrap-around solution from January to December is thus also implemented.
        Source: NYMEX
        """
        # Here we handle the wrap-around from January to December.
        if self.delivery_month.month.month == 1:
            expiry_month = 12
            expiry_year = self.delivery_month.month.year - 1
        else:
            expiry_month = self.delivery_month.month.month - 1
            expiry_year = self.delivery_month.month.year

        expiry_day = 25  # 25th is the day we start counting from.

        # Construct the target date (the 25th of the expiry month).
        target_date = pd.Timestamp(year=expiry_year, month=expiry_month, day=expiry_day)

        # Subtract 3 business days from the target date to get the expiry date.
        third_business_day_before = target_date - 3 * self.us_bd

        return third_business_day_before

    def calculate_gas_expiry(self):
        """
        Calculates the expiry date for a Natural Gas future.
        The expiration date is three business days prior to the first day of the delivery month.
        Source: NYMEX
        """
        # Construct the target date (the 1st of the delivery month).
        target_date = pd.Timestamp(year=self.delivery_month.month.year, month=self.delivery_month.month.month, day=1)

        # Subtract 3 business days from the target date to get the expiry date.
        third_business_day_before = target_date - 3 * self.us_bd

        return third_business_day_before

    @property
    def time_to_expiration(self):
        """
        Determines the time to expiration of the future.
        Depending on the type of the future (Crude Oil or Natural Gas), it uses different rules for determining the expiry date.
        """
        # If the future is Crude Oil, use the oil-specific rule.
        if self.underlying_future.name == 'Crude Oil':
            expiry_date = self.calculate_oil_expiry()

        # If the future is Natural Gas, use the gas-specific rule.
        elif self.underlying_future.name == 'Natural Gas':
            expiry_date = self.calculate_gas_expiry()

        # If the future is neither Crude Oil nor Natural Gas, raise an error.
        else:
            raise ValueError(f'Unknown underlying future: {self.underlying_future.name}')

        # Calculate the number of days until expiry and convert this to years.
        delta = expiry_date - pd.Timestamp.now()
        time_to_expiration = delta.days / 365.0  # convert to years

        # Check that the time to expiration is positive and non-zero.
        if time_to_expiration <= 0:
            raise ValueError('Time to expiration must be positive and non-zero')

        return time_to_expiration

    def calculate_option_price(self):
        # Retrieve latest futures settlement price based on delivery month and future type
        market_data = MarketData.objects.filter(
            product_name = self.underlying_future.name,
            delivery_month = self.delivery_month.month
            
        ).order_by('-settlement_date').first()

        if not market_data:
            raise ValueError("No market data found for this option")
        
        F = float(market_data.futures_price) # Latest futures price for option

        K = float(self.strike_price) # Strike price from Option model

        T = self.time_to_expiration # Time to expiration in years

        r = 0.05 # Risk free rate

        sigma = 0.20 # volatility

        # Black 76 Formula

        d1 = (math.log(F / K) + (0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if self.option_type == 'CALL':
            option_price = math.exp(-r * T) * (F * si.norm.cdf(d1) - K * si.norm.cdf(d2))
        elif self.option_type == 'PUT':
            option_price = math.exp(-r * T) * (K * si.norm.cdf(-d2) - F * si.norm.cdf(-d1))
        else:
            raise ValueError(f'Unknown option type: {self.option_type}')

        return option_price
        

    def __str__(self):
        return f"{self.option_type} {self.underlying_future} {self.delivery_month}"


