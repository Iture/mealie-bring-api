import asyncio
import sys

import aiohttp
from bring_api import Bring, BringItemOperation, BringNotificationType
from environment_variable_getter import EnvironmentVariableGetter
from ingredient import Ingredient
from logger_mixin import LoggerMixin
from thefuzz import process

class BringHandler(LoggerMixin):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()

        self.bring = loop.run_until_complete(self.initialize())
        self.list_uuid = loop.run_until_complete(self.determine_list_uuid())
        

    async def initialize(self) -> Bring:
        username = EnvironmentVariableGetter.get("BRING_USERNAME")
        password = EnvironmentVariableGetter.get("BRING_PASSWORD")

        session = aiohttp.ClientSession()
        bring = Bring(session, username, password)
        self.log.info("Attempting the login into Bring")
        await bring.login()
        self.log.info("Login successful")
        
        return bring

    async def determine_list_uuid(self) -> str:
        list_name = EnvironmentVariableGetter.get("BRING_LIST_NAME")
        list_name_lower = list_name.lower()
        for bring_list in (await self.bring.load_lists())["lists"]:
            if bring_list["name"].lower() == list_name_lower:
                bring_list_uuid = bring_list["listUuid"]
                self.log.info(f'Found the list with the name "{list_name}" (UUID: {bring_list_uuid})')
                return bring_list_uuid
        
        self.log.critical(f'Can not find a list with the name "{list_name}"')
        sys.exit(1)

    async def add_items(self, ingredients: list[Ingredient]) -> None:
        if EnvironmentVariableGetter.get("USE_FUZZY_MATCHING","true") == "true":
            await self.translate_item_names(ingredients)
        items = [ingredient.to_dict() for ingredient in ingredients]
        await self.bring.batch_update_list(self.list_uuid, items, BringItemOperation.ADD)

    async def notify_users_about_changes_in_list(self) -> None:
        self.log.debug("Notifying users about changes in shopping list")
        await self.bring.notify(self.list_uuid, BringNotificationType.CHANGED_LIST)
    
    async def translate_item_names(self,ingredients: list[Ingredient]) -> None:
        self.log.debug("Translating item names")
        product_names = self.bring._Bring__translations
        if not product_names: return

        product_name_values = product_names[next(iter(product_names))].values()        
        for ingredient in ingredients:
            ingredient_name = ingredient.name
            # Find the best match for the ingredient name in product_name_values
                
            best_match, score = process.extractOne(ingredient_name, product_name_values)
            
            # Replace the ingredient name with the best match if score is above threshold, add base name to specification
            #TODO Add threshold to configuration
            if score >= 85:  # Threshold can be adjusted based on needs
                
                ingredient.specification = ingredient_name + " " + ingredient.specification if score < 100 else ingredient.specification
                ingredient.name = best_match
                self.log.debug(f"Translating '{ingredient_name}' to '{best_match}' (score: {score})")
                self.log.debug(f"Ingredient spec '{ingredient.specification}'")
            else:
                self.log.debug(f"No good match found for '{ingredient_name}' (best: '{best_match}', score: {score})")
