import asyncio
import re
import time
import random
import os  # Import os
import sys # Import sys
from DrissionPage import Chromium, ChromiumOptions  # Corrected import
from rich.console import Console
from datetime import datetime

console = Console()

STATE_MAPPING = {
    'ALABAMA': 'AL', 'ALASKA': 'AK', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR', 'CALIFORNIA': 'CA',
    'COLORADO': 'CO', 'CONNECTICUT': 'CT', 'DELAWARE': 'DE', 'FLORIDA': 'FL', 'GEORGIA': 'GA',
    'HAWAII': 'HI', 'IDAHO': 'ID', 'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA',
    'KANSAS': 'KS', 'KENTUCKY': 'KY', 'LOUISIANA': 'LA', 'MAINE': 'ME', 'MARYLAND': 'MD',
    'MASSACHUSETTS': 'MA', 'MICHIGAN': 'MI', 'MINNESOTA': 'MN', 'MISSISSIPPI': 'MS', 'MISSOURI': 'MO',
    'MONTANA': 'MT', 'NEBRASKA': 'NE', 'NEVADA': 'NV', 'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ',
    'NEW MEXICO': 'NM', 'NEW YORK': 'NY', 'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND', 'OHIO': 'OH',
    'OKLAHOMA': 'OK', 'OREGON': 'OR', 'PENNSYLVANIA': 'PA', 'RHODE ISLAND': 'RI', 'SOUTH CAROLINA': 'SC',
    'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN', 'TEXAS': 'TX', 'UTAH': 'UT', 'VERMONT': 'VT',
    'VIRGINIA': 'VA', 'WASHINGTON': 'WA', 'WEST VIRGINIA': 'WV', 'WISCONSIN': 'WI', 'WYOMING': 'WY'
}

def format_zillow_url(location: str) -> str:
    """Formats a location string into a Zillow-friendly URL format"""
    location = location.strip().lower()
    location = re.sub(r'\s+', '-', location)
    location = re.sub(r'[^\w\s-]', '', location)
    return f"https://www.zillow.com/homes/{location}_rb/"

async def validate_location_search(search_query: str) -> tuple[bool, str, str]:
    """Validates and formats a location search query"""
    cleaned_query = re.sub(r'\s+', ' ', search_query.strip())

    if not cleaned_query:
        return False, "", "Search query cannot be empty"

    location_parts = [part.strip() for part in cleaned_query.split(',')]

    if len(location_parts) != 2:
        return False, "", "Please enter both city and state (e.g., 'Los Angeles, California')"

    city = ' '.join(word.capitalize() for word in location_parts[0].split())
    state = location_parts[1].strip().upper()

    if len(state) > 2:
        state = STATE_MAPPING.get(state)
        if not state:
            return False, "", "Invalid state name. Please enter a valid US state"
    elif len(state) != 2:
        return False, "", "Invalid state format. Please enter full state name or two-letter code"

    formatted_location = f"{city}, {state}"
    zillow_url = format_zillow_url(formatted_location)

    return True, formatted_location, zillow_url

async def scrape_zillow_data(zillow_url: str, max_pages: int = 2):
    """Scrapes Zillow property data with minimal browser configurations"""
    co = ChromiumOptions()
    
    # Set window size at startup
    co.set_argument('--window-size=960,720')
    
    # Headless mode and other settings
    co.set_argument('--headless=new')
    co.set_argument('--log-level=0')
    co.set_argument('--disable-features=VizDisplayCompositor')
    
    # Set a more realistic user agent
    co.set_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    co.set_pref("credentials_enable_service", False)
    co.auto_port()  # Use a random port

    # Create Chromium object directly with the configured options
    browser = Chromium(addr_or_opts=co)
    if not browser.states.is_alive:
        console.print("[red]Error: Browser process failed to start.[/red]")
        return []

    tab = browser.get_tab()
    
    # Remove debug window size verification
    tab.get("about:blank")
    
    properties_data = []
    total_properties = 0
    current_page = 1
    scrape_all_pages = (max_pages == -1)
    previous_page_last_property_id = None
    should_continue_scraping = True
    all_properties = set()  # Keep track of ALL properties across pages
    max_properties_per_page = 41  # Zillow's max properties per page
    
    try:
        console.print("\n[bold blue]Starting Zillow Property Scraper[/bold blue]")
        console.print("[dim]Press Ctrl+C to stop at any time[/dim]\n")

        while should_continue_scraping and (scrape_all_pages or current_page <= max_pages):
            console.print(f"[yellow]━━ Scraping page {current_page} of {'all' if scrape_all_pages else max_pages} ━━[/yellow]")
            
            retry_count = 0
            max_retries = 1
            properties_found_this_page = 0
            
            while retry_count <= max_retries:
                if current_page == 1:
                    console.print("[cyan]Navigating to Zillow...[/cyan]")
                    tab.get(zillow_url)
                    console.print("[yellow]Waiting until page fully loads (anti-bot)...[/yellow]")
                    # Take screenshot after initial page load
                    tab.get_screenshot(path='.', name=f'page_{current_page}_initial.png')
                    # Get total results count on first page
                    try:
                        results_element = tab.ele('.result-count')
                        total_results = int(''.join(filter(str.isdigit, results_element.text)))
                        expected_total_pages = (total_results + max_properties_per_page - 1) // max_properties_per_page
                        # Calculate remaining properties for current page
                        remaining_properties = total_results - (current_page - 1) * max_properties_per_page
                        expected_properties = min(max_properties_per_page, remaining_properties)
                        console.print(f"[cyan]Total results: {total_results}, Expected properties on this page: {expected_properties}[/cyan]")
                    except Exception as e:
                        console.print(f"[red]Error getting total results count: {str(e)}[/red]")
                        expected_properties = max_properties_per_page
                else:
                    console.print("[cyan]Navigating to next page...[/cyan]")
                    # Calculate remaining properties for subsequent pages
                    remaining_properties = total_results - (current_page - 1) * max_properties_per_page
                    expected_properties = min(max_properties_per_page, remaining_properties)
                    console.print(f"[cyan]Total results: {total_results}, Previously scraped: {len(properties_data)}, Expected on this page: {expected_properties}[/cyan]")
                    await asyncio.sleep(0.5)

                try:
                    tab.wait.doc_loaded(timeout=5)
                    if not tab.wait.ele_displayed('css:[data-test="property-card"]', timeout=5):
                        if current_page > 1:
                            console.print("[yellow]Retrying page load...[/yellow]")
                            tab.refresh()
                            await asyncio.sleep(1)
                            if not tab.wait.ele_displayed('css:[data-test="property-card"]', timeout=5):
                                break
                        else:
                            break
                except Exception as e:
                    console.print(f"[red]Error loading page: {str(e)}[/red]")
                    break

                # Scroll until we find the next button or reach bottom
                last_count = 0
                scroll_attempts = 0
                max_scroll_attempts = 2  # Original scroll + 1 retry from top

                while scroll_attempts < max_scroll_attempts:
                    while True:
                        property_cards = tab.eles('css:[data-test="property-card"]')
                        current_count = len(property_cards)
                        
                        # Process only new cards
                        for card in property_cards[last_count:]:
                            try:
                                address = card('t:address').text.strip()
                                price = card('@data-test=property-card-price').text.strip()
                                
                                property_id = f"{address}|{price}"
                                if property_id in all_properties:  # Check against all properties
                                    continue

                                all_properties.add(property_id)  # Add to all properties set
                                
                                details = card('t:ul').eles('t:li')
                                beds = baths = sqft = "N/A"
                                
                                if details:
                                    for detail in details:
                                        text = detail.text.strip()
                                        if 'bd' in text:
                                            beds = text.split()[0]
                                            beds = "N/A" if beds == "--" else beds.replace('bds', '').replace('bd', '')
                                        elif 'ba' in text:
                                            baths = text.split()[0]
                                            baths = "N/A" if baths == "--" else baths.replace('ba', '')
                                        elif 'sqft' in text:
                                            sqft = text.split()[0]
                                            sqft = "N/A" if sqft == "--" else sqft.replace('sqft', '').replace(',', '')

                                properties_data.append({
                                    'address': address,
                                    'price': "N/A" if price == "--" else price.replace('$', '').replace(',', ''),
                                    'beds': beds,
                                    'baths': baths,
                                    'sqft': sqft
                                })
                                properties_found_this_page += 1
                                
                            except Exception as e:
                                continue

                        last_count = current_count

                        # Check for next button visibility
                        try:
                            next_button = tab.ele('css:a[rel="next"]')
                            if not next_button:
                                next_button = tab.ele('css:a[title="Next page"]')
                                if not next_button:
                                    next_button = tab.ele('css:.search-pagination a:last-child')
                            
                            if next_button and next_button.is_displayed():
                                console.print("[cyan]Found next page button - finished scrolling[/cyan]")
                                break
                        except:
                            pass

                        # Simple scroll down by a fixed amount - using original method
                        tab.scroll.down(900)
                        await asyncio.sleep(0.3)

                        # Check if we got new cards after scroll
                        new_count = len(tab.eles('css:[data-test="property-card"]'))
                        if new_count == current_count:
                            break

                    # If we got enough properties, no need to retry
                    if properties_found_this_page >= expected_properties:
                        break

                    # If this was the first attempt and we didn't get enough properties,
                    # scroll back to top and try again
                    if scroll_attempts == 0 and properties_found_this_page < expected_properties:
                        console.print(f"[yellow]Found {properties_found_this_page} properties, expected {expected_properties}. Scrolling from top again...[/yellow]")
                        tab.scroll.to_top()
                        await asyncio.sleep(0.5)  # Wait for page to stabilize
                        last_count = 0  # Reset counter to reprocess all cards
                        scroll_attempts += 1
                    else:
                        break

                # After processing the page
                if properties_found_this_page > 0:
                    current_page_last_property_id = f"{properties_data[-1]['address']}|{properties_data[-1]['price']}"
                    if current_page_last_property_id == previous_page_last_property_id:
                        console.print("[yellow]Detected repetition of last page. Stopping.[/yellow]")
                        should_continue_scraping = False
                        total_properties += properties_found_this_page
                        console.print(f"[green]✓ Page {current_page}: Successfully scraped {properties_found_this_page} properties[/green]")
                        console.print("─" * 50 + "\n")
                        break

                    previous_page_last_property_id = current_page_last_property_id

                # Continue with pagination
                if should_continue_scraping:
                    total_properties += properties_found_this_page
                    console.print(f"[green]✓ Page {current_page}: Successfully scraped {properties_found_this_page} properties[/green]")
                    console.print("─" * 50 + "\n")

                    if scrape_all_pages or current_page < max_pages:
                        try:
                            next_button = tab.ele('css:a[rel="next"]')
                            if not next_button:
                                next_button = tab.ele('css:a[title="Next page"]')
                                if not next_button:
                                    next_button = tab.ele('css:.search-pagination a:last-child')

                            if not next_button:
                                break

                            if next_button.attr('aria-disabled') == 'true':
                                console.print("[yellow]Next button disabled. End of pagination.[/yellow]")
                                break

                            current_url = tab.url
                            next_button.click()
                            tab.wait.url_change(current_url, timeout=15)
                            # Reset page-specific variables before moving to next page
                            properties_found_this_page = 0  # Reset counter
                            current_page += 1
                            # Reset scroll attempts for the new page
                            scroll_attempts = 0
                            last_count = 0
                        except Exception as e:
                            break
                    else:
                        break

            console.print("\n[bold green]━━━ Scraping Complete! ━━━[/bold green]")
            console.print(f"[bold]Total Pages Scraped: [cyan]{current_page}[/cyan][/bold]")
            console.print(f"[bold]Total Properties Found: [cyan]{total_properties}[/cyan][/bold]\n")

            return properties_data

    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        return []
    finally:
        browser.quit()
