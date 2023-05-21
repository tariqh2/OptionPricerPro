from django.shortcuts import render
from .models import Option, MarketData, DeliveryMonth
from .forms import OptionForm, DateRangeForm
from django.http import JsonResponse
from django.views import View
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import json
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages

# Define the index view that is responsible for rendering the form to the user and processing the form submission
def index(request):
    # Check if the request is a POST request, indicating a form submission
    if request.method == "POST":
        # Bind the form with the submitted POST data
        form = OptionForm(request.POST)
        # Validate the form data
        if form.is_valid():
            # Save the form and get the Option object
            option = form.save()
            try:
                option_price = option.calculate_option_price()
            except ValueError as e:
                messages.error(request, "Time to expiry must be positive and non-zero.")
                return render(request, 'index.html', {'form': form})
            # Calculate the option price and time to expiration
            option_price = option.calculate_option_price()
            time_to_expiration = option.time_to_expiration
            # Render the template with the calculated values
            return render(request, 'index.html', {
                'form': form,
                'option_price': option_price,
                'time_to_expiration': time_to_expiration,
                'option_type': option.option_type,
                'underlying_future': option.underlying_future,
                'delivery_month': option.delivery_month,
                'strike_price': option.strike_price
            })
    else:  # If it's not a POST request, render the form without any data
        form = OptionForm()

    return render(request, 'index.html', {
        'form': form
        
        })

# Define the view for fetching market data from the API

US_BUSINESS_DAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())

def refresh_data(request):
    if request.method == 'POST':
        print('Received a POST request')
        start_date = request.POST.get('startDate')
        end_date = request.POST.get('endDate')

        # connect to the API and fetch data...
        api_key = "jO6br3aYk2fQEeEEzdeI3UGkIWUMs8wsSKFgpwud"
        endpoint = "https://api.eia.gov/v2/petroleum/pri/fut/data/"
        params = {
            "api_key": api_key,
            "frequency": "daily",
            "data[0]": "value",
            "facets[series][]": "RCLC1",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": 5000,
            "start": start_date,
            "end": end_date
        }
        response = requests.get(endpoint, params=params)
        data = response.json()
        print('API response:', data)

        # parse the data and create the market_data list as before...
        market_data = []
        if 'data' in data['response']:
            print('Data found in API response')
            for row in data['response']['data']:
                settlement_date_str = row['period']
                product_name = row['product-name']
                delivery_month_str = row['process-name']
                futures_price = row['value']
        
                settlement_date = datetime.strptime(settlement_date_str, '%Y-%m-%d').date()
                if delivery_month_str == 'Future Contract 1':
                    delivery_month = datetime.strptime(settlement_date_str, '%Y-%m-%d').date()
                    delivery_month = delivery_month + relativedelta(months=2)
                    if delivery_month.day >= 25:
                        target_date = delivery_month.replace(day=25)
                        if pd.bdate_range(start=target_date, end=target_date, freq=US_BUSINESS_DAY).empty:
                            target_date -= 3 * US_BUSINESS_DAY
                        while pd.bdate_range(start=target_date, end=target_date, freq=US_BUSINESS_DAY).empty:
                            target_date -= US_BUSINESS_DAY
                        delivery_month = target_date + relativedelta(months=3)
                    delivery_month = delivery_month.replace(day=1)
        
                market_data.append({
                    'settlement_date': settlement_date,
                    'product_name': product_name,
                    'delivery_month': delivery_month,
                    'futures_price': futures_price
                })

        # Save the data to the MarketData model
        for data in market_data:
            print('Saving data:', data)
            delivery_month, created = DeliveryMonth.objects.get_or_create(month=data['delivery_month'])
            MarketData.objects.create(
                settlement_date=data['settlement_date'],
                product_name=data['product_name'],
                delivery_month=data['delivery_month'],
                futures_price=data['futures_price']
            )
        print('Finished saving data')

        # Add a success message
        messages.success(request, 'Data refresh successful')
        
        return HttpResponseRedirect(reverse('index'))

    else:
        print('Received a non-POST request')

        messages.error(request, 'Market data refresh failed: not a POST request')
        return HttpResponseRedirect(reverse('index'))
        
