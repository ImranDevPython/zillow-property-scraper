import asyncio
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.table import Table
from typing import List, Dict, Any, Tuple

from scraper.zillow import validate_location_search, scrape_zillow_data
from data.storage import DataStorage

console = Console()

class ZillowCLI:
    """
    Command-line interface for the Zillow Property Scraper.
    """
    def __init__(self):
        self.storage = DataStorage()
    
    async def get_search_location(self) -> Tuple[str, str]:
        """
        Interactive CLI function to get and validate search location
        Returns (formatted_location, zillow_url)
        """
        while True:
            search_query = console.input(
                "[bold blue]Enter location to search[/bold blue]\n"
                "[dim]Format: 'Location, State' (e.g., 'New Tampa, Florida' or 'Brooklyn, NY')\n"
                "Location can be a city, neighborhood, or area[/dim] "
                ":::[cyan]:::[/cyan] "
            )

            is_valid, formatted_location, result = await validate_location_search(search_query)

            if is_valid:
                console.print(f"[green]Using location: {formatted_location}[/green]")
                return formatted_location, result
            else:
                console.print(f"[red]{result}[/red]")
                suggestion = Prompt.ask(
                    "[yellow]Would you like to try another search?[/yellow]",
                    choices=["yes", "no"],
                    default="yes"
                )
                if suggestion.lower() != "yes":
                    raise ValueError("Search cancelled by user")
    
    def display_property_table(self, properties: List[Dict[str, Any]]) -> None:
        """Display properties in a rich table format."""
        if not properties:
            console.print("[yellow]No properties to display.[/yellow]")
            return
        
        table = Table(title="Property Listings")
        table.add_column("#", style="cyan", justify="right")
        table.add_column("Address", style="yellow")
        table.add_column("Price", style="green")
        table.add_column("Beds", style="magenta")
        table.add_column("Baths", style="magenta")
        table.add_column("Sq.Ft.", style="blue")
        
        for i, prop in enumerate(properties, 1):
            # Clean up the values before displaying
            beds = prop['beds'].replace('bds', '').replace('bd', '') if prop['beds'] != 'N/A' else 'N/A'
            beds = 'N/A' if beds == '--' else beds
            
            baths = prop['baths'].replace('ba', '') if prop['baths'] != 'N/A' else 'N/A'
            baths = 'N/A' if baths == '--' else baths
            
            sqft = prop['sqft'].replace('sqft', '') if prop['sqft'] != 'N/A' else 'N/A'
            sqft = 'N/A' if sqft == '--' else sqft
            
            # Format price with $ and handle N/A
            if prop['price'] == 'N/A':
                price = 'N/A'
            else:
                price = f"${prop['price']}"
            
            table.add_row(
                str(i),
                prop['address'],
                price,
                beds,
                baths,
                sqft
            )
        
        console.print(table)
    
    async def export_menu(self, properties: List[Dict[str, Any]], location: str) -> None:
        """Display export options menu and handle user choice."""
        if not properties:
            console.print("[yellow]No properties to export.[/yellow]")
            return
        
        choice = Prompt.ask(
            "\n[bold blue]Export Options[/bold blue]",
            choices=["csv", "json", "both", "skip"],
            default="csv"
        )
        
        if choice == "csv" or choice == "both":
            self.storage.export_to_csv(properties, location)
        
        if choice == "json" or choice == "both":
            self.storage.export_to_json(properties, location)
        
        if choice == "skip":
            console.print("[yellow]Export skipped.[/yellow]")
    
    async def run(self) -> None:
        """Run the main CLI interface."""
        console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
        console.print("[bold blue]   Zillow Property Scraper - CLI Interface   [/bold blue]")
        console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]\n")
        
        try:
            # Get location to search
            location, zillow_url = await self.get_search_location()
            
            max_pages_input = Prompt.ask(
                "[bold blue]How many pages to scrape? (Enter 'all' for all pages)[/bold blue]",
                default="2"
            )
            try:
                max_pages = int(max_pages_input)
            except ValueError:
                if max_pages_input.lower() == 'all':
                    max_pages = -1
                else:
                    console.print("[red]Invalid input. Please enter a number or 'all'.[/red]")
                    raise
            
            properties = await scrape_zillow_data(zillow_url, max_pages)
            
            self.display_property_table(properties)
            
            # Export options
            await self.export_menu(properties, location)
            
            console.print("\n[bold green]Thank you for using Zillow Property Scraper![/bold green]")
            
        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
