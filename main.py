# IMPORTS
import asyncio
import datetime
import discord
import random
import sqlite3
import re

from table2ascii import table2ascii as t2a, Alignment
# from discord import app_commands
from discord.ext import commands, tasks
from config import settings, jokes_db, admin_db

# TODO: convert commands to slash commands with
# discord.app_commands.CommandTree.
# https://stackoverflow.com/questions/71165431/how-do-i-make-a-working-slash-command-in-discord-py

# VARIABLES
# Change only the no_category default string
help_command = commands.DefaultHelpCommand(no_category='Commands', indent=3)

# set bot commands prefix and number of shards
bot_prefix = settings['prefix']
bot_shards = settings['shards']


intents = discord.Intents.all()
intents.message_content = True
intents.messages = True

# customize bot with prefix and custom help
# bot_client = discord.Bot(intents=intents, help_command=help_command)
bot_client = commands.AutoShardedBot(command_prefix=lambda bot, msg: ['/'],
                                     help_command=help_command,
                                     shard_count=bot_shards,
                                     intents=intents)

# global var
guilds_number = 0
# commands short description list
cmd_brief = {
    "about": "Show info about the bot",
    "stat": "Show bot statistics",
    "hello": "Show welcome message",
    "joke": "Get a DnD joke",
    "roll": "Roll the dice",
    "mod": "Roll the dice with modifiers",
    "d": "Roll single die",
    "prefix": "Manage bot prefix (admin only)",
    "prefix_set": "Set new prefix for the bot commands",
    "prefix_restore": "Restore default prefix"
}

# commands long description list
cmd_help = {
    "about": "Show bot version, Privacy Policy, link on Github, link on top.gg etc",
    "stat": "Show number of shards, number of servers using it etc",
    "hello": "Dice Roller greetings you and tell a little about himself.",
    "joke": "Bot post a random DnD joke from database (soon you will get opportunity to add yours jokes).",
    "roll": f"Roll different type of dice in one roll:\n \
            - single die, single roll: d20\n \
            - single die, multiple rolls: 10d4\n \
            - multiple dice, single roll: d4 d8 d20\n \
            - multiple dice, multiple rolls: 4d8 4d4 2d20\n \
            - fate dice: fate dF 6dF\n \
            - exploding dice: explode Ed20 E4d10\n \
            - co-co-combo: d20 5d10 fate d123 Ed8",
    "mod": f"Roll different type of dice with mods in one roll:\n \
            - single die, single roll: d20+1\n \
            - single die, multiple rolls: 10d4-2\n \
            - multiple dice, single roll: d4-1 d20+2 d100-10\n \
            - multiple dice, multiple roll: 5d4+1 2d20-2 4d6-1\n \
            - fate dice: fate 4dF+1 10dF-2\n \
            - exploding dice: explode Ed20-4 Ed6+1\n \
            - co-co-combo: d20 5d10-2 2d100 fate d123+5 Ed10-2",
    "d": f"Single roll of single type die: \n \
            - 20\n \
            - 8\n \
            - 100",
    "prefix": "Manage prefix for the bot commands",
    "prefix_set": "Set new prefix",
    "prefix_restore": "Restore default prefix"
}

# commands usage list
cmd_usage = {
    "roll": "dice_1 [dice_2 ... dice_n]",
    "mod": "dice_1 [dice_2 ... dice_n]"
}

cmd_alias = {
    "about": ["bot", "version"],
    "stat": ["s"],
    "hello": ["sup", "hi", "Hello"],
    "joke": ["j", "J", "Joke"],
    "roll": ["r", "R", "Roll"],
    "mod": ["m", "M", "Mod"],
    "d": ["D"],
    "prefix": ["p", "P"],
    "prefix_set": ["s"],
    "prefix_restore": ["r"]
}

suffix_verbs = ['pass']
mod_types = ['pass', 'add', 'sub']
spec_dice = {
    "fate": "4dF",
    "explode": "Ed6"
}

limits = {
    "dice": 20,
    "edge": 1000000000,
    "mod": 1000000000,
    "adds": 3,
    "prefix": 3,
    "roll": 50
}

# db part
# TODO: make log system more common (not just print command)
conn = sqlite3.connect(jokes_db)
cursor = conn.cursor()
sql = "SELECT COUNT(joke_id) FROM jokes;"
number_of_jokes = 1


# FUNCTIONS
# check int
def check_int(possibly_int):
    try:
        exactly_int = int(possibly_int)
    except ValueError:
        raise commands.BadArgument
    else:
        return exactly_int


# override negative
def check_subzero(possibly_subzero):
    number = possibly_subzero
    if int(number) < 0:
        number = 0
    return number


# check zero and negative
def check_one(possibly_zero_or_less):
    if possibly_zero_or_less < 1:
        raise commands.BadArgument


# sad but we need limits
def check_limit(number, limit):
    if number > limit:
        raise commands.ArgumentParsingError


def split_dice_with_mod(dice):
    dice_split_args = re.split(r'([+-])', dice)
    adds = []
    dice_args_len = len(dice_split_args)
    dice_without_adds = dice_split_args[0]
    if dice_args_len > 1:
        adds_list = dice_split_args[1:]
        raw_adds = make_batch(adds_list, 2)
        for add in raw_adds:
            if len(add) != 2:
                raise commands.ArgumentParsingError
            if add[1] != '':
                adds.append(add)
        check_limit(len(adds), limits["adds"])
    return dice_without_adds, adds


# ident explode rolls
def ident_explode(rolls):
    rolls = rolls.lower()
    explode_rolls = rolls.split('e')
    if len(explode_rolls) != 2:
        raise commands.BadArgument
    number_of_rolls = explode_rolls[1]
    if number_of_rolls == '':
        number_of_rolls = 1
    number_of_rolls = check_int(number_of_rolls)
    return number_of_rolls


# split and check dice for rolls and edges
def ident_dice(dice):
    dice_type = []
    rolls_and_edges = dice.split('d')
    if len(rolls_and_edges) != 2:
        raise commands.BadArgument
    dice_rolls = rolls_and_edges[0]
    dice_edge = rolls_and_edges[1]
    if dice_rolls[0].lower() == 'e':
        explode_rolls = ident_explode(dice_rolls)
        dice_type.append('explode')
        dice_rolls = explode_rolls
        check_limit(dice_rolls, limits["roll"])
    else:
        if dice_rolls == '':
            dice_rolls = 1
        dice_rolls = check_int(dice_rolls)
        check_one(dice_rolls)
        check_limit(dice_rolls, limits["roll"])
    if dice_edge.lower() == 'f':
        dice_type.append('fate')
        dice_edge = dice_edge.upper()
    else:
        dice_edge = check_int(dice_edge)
        check_one(dice_edge)
        check_limit(dice_edge, limits["edge"])
    return dice_rolls, dice_edge, dice_type


# roll dice
def dice_roll(rolls, edge):
    dice_roll_result = []
    for counts in range(1, rolls + 1):
        roll_result = random.randint(1, edge)
        dice_roll_result.append(roll_result)
    return dice_roll_result


# fate roll
def fate_roll(rolls):
    dice_roll_result = []
    for counts in range(1, rolls + 1):
        roll_result = random.choices(["+", ".", "-"])
        dice_roll_result += roll_result
    return dice_roll_result


def fate_result(dice_result):
    total_result = dice_result.count('+') - dice_result.count('-')
    return total_result


# explode roll
def explode_roll(rolls, edge):
    if edge < 2:
        raise commands.BadArgument
    dice_roll_result = []
    for counts in range(1, rolls + 1):
        check = edge
        while check == edge:
            roll_result = random.randint(1, edge)
            dice_roll_result.append(roll_result)
            check = roll_result
    return dice_roll_result


# summarize result
def calc_result(dice_result):
    total_result = sum(dice_result)
    return total_result


# mod rolls result
def add_mod_result(total_result, mod_amount):
    total_mod_result = total_result + mod_amount
    return total_mod_result


def sub_mod_result(total_result, mod_amount):
    total_mod_result = total_result - mod_amount
    total_mod_result = check_subzero(total_mod_result)
    return total_mod_result


def sub_mod_fate(total_result, mod_amount):
    total_mod_result = total_result - mod_amount
    return total_mod_result


# create row for table output
def create_row(*args):
    table_row = []
    for item in args:
        table_row.append(item)
    return table_row


# create table from rows
def create_table(table_body):
    if len(table_body[0]) == 3:
        table_header = create_row('dice', 'rolls', 'sum')
    elif len(table_body[0]) == 4:
        table_header = create_row('dice', 'rolls', 'mods', 'sum')
    else:
        table_header = create_row('dice', 'result')
    columns = len(table_header) - 1
    output = t2a(
        header=table_header,
        body=table_body,
        first_col_heading=True,
        alignments=[Alignment.LEFT] + [Alignment.CENTER] * columns
    )
    return output


# add [] around sum number
def make_pretty_sum(not_so_pretty):
    pretty_sum = '[' + str(not_so_pretty) + ']'
    return pretty_sum


# make string from list for pretty rolls output
def make_pretty_rolls(not_so_pretty):
    delimiter = ' '
    size = 8
    pretty_rolls = ''
    if len(not_so_pretty) > size:
        batch_rolls = make_batch(not_so_pretty, size)
        for batch in batch_rolls:
            pretty_rolls += delimiter.join(str(r) for r in batch)
            pretty_rolls += '\n'
    else:
        pretty_rolls = delimiter.join(str(x) for x in not_so_pretty)
    return pretty_rolls


# let split longs for shorts
def make_batch(origin_list, size):
    new_list = []
    for i in range(0, len(origin_list), size):
        new_list.append(origin_list[i:i + size])
    return new_list


# make things shorter
def make_short(original_string, size=5):
    new_string = str(original_string)
    if len(new_string) > size:
        new_string = new_string[:2] + '..' + new_string[-1:]
    return new_string


# make dice label for table from args
def dice_maker(*args):
    args_list = list(args)
    result = ''
    if args_list[0] == 1:
        args_list = args_list[1:]
    for arg in args_list:
        result += str(arg)
    return result


# get prefix
def prefix_for_help(message):
    guild_id = str(message.guild.id)
    db = sqlite3.connect(admin_db)
    cur = db.cursor()
    prefix_sql = "SELECT guild_prefix FROM guild_prefixes WHERE guild_id = ?;"
    cur.execute(prefix_sql, [guild_id])
    guild_prefix = cur.fetchone()
    if guild_prefix is not None:
        guild_prefix = guild_prefix[0]
    else:
        guild_prefix = bot_prefix
    db.close()
    return guild_prefix


# EVENTS
# on connect actions
@bot_client.event
async def on_connect():
    # log connection info
    print(datetime.datetime.now(), 'INFO', 'Bot connected')


# on ready actions
@bot_client.event
async def on_ready():
    # log ready info
    print(datetime.datetime.now(), 'INFO', 'Bot ready')
    # log connected guilds number
    print(datetime.datetime.now(), 'INFO', 'Number of servers connected to:', bot_client.guilds)
    await bot_client.change_presence(activity=discord.Activity(name='dice rolling!',
                                                               type=discord.ActivityType.competing))
    await asyncio.sleep(10)
    # start number of jokes update loop
    update_jokes.start()
    await asyncio.sleep(10)
    # start status update loop
    update_guild_number.start()


# wrong commands handler
@bot_client.event
async def on_command_error(ctx, error):
    author = ctx.message.author
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f'{author.mention}, command not found.\n'
                       f'Please, use the "{bot_prefix}help" command to get full list of commands.')


# top.gg successful post event
@bot_client.event
async def on_autopost_success():
    print(datetime.datetime.now(), 'INFO', 'Posted server count on Top.gg')


# LOOPS
# status update loop
@tasks.loop(hours=1)
async def update_guild_number():
    print(datetime.datetime.now(), 'INFO', 'Bot status updated, current number:', len(bot_client.guilds))
    global guilds_number
    guilds_number = len(bot_client.guilds)


# number of jokes update loop
@tasks.loop(hours=1)
async def update_jokes():
    cursor.execute(sql)
    global number_of_jokes
    number_of_jokes = cursor.fetchone()[0]
    print(datetime.datetime.now(), 'INFO', 'Jokes number updated, current number:', number_of_jokes)
    return number_of_jokes

# USER COMMANDS AND ERRORS HANDLERS
# JOKE COMMAND
@bot_client.command(brief=cmd_brief["joke"], help=cmd_help["joke"], aliases=cmd_alias["joke"])
# @bot_client.slash_command(brief=cmd_brief["joke"], help=cmd_help["joke"], aliases=cmd_alias["joke"])
async def joke(ctx):
    random_joke_number = random.randint(1, number_of_jokes)
    sql_joke = "SELECT joke_text FROM jokes WHERE joke_id=?;"
    cursor.execute(sql_joke, [random_joke_number])
    joke_text = cursor.fetchone()[0]
    await ctx.send('Today joke is:\n' + joke_text)


# D COMMAND
@bot_client.command(brief=cmd_brief["d"], help=cmd_help["d"], aliases=cmd_alias["d"])
async def d(ctx, dice_edge):
    # prepare empty list for future output lines storing
    output_body = []
    # always single roll for d command
    rolls = 1
    # necessary checks: should be int, 1 or more and less than limit for edges
    edge = check_int(dice_edge)
    check_one(edge)
    check_limit(edge, limits["edge"])
    # roll
    roll_result = dice_roll(rolls, edge)
    # prepare dice for output
    output_dice = dice_maker('d', edge)
    # convert roll into list
    output_roll_result = make_pretty_rolls(roll_result)
    # create row for output
    table_row = create_row(output_dice, output_roll_result)
    # append rows
    output_body.append(table_row)
    # create table
    output = create_table(output_body)
    # send it into chat
    await ctx.send(f"```{output}```")


# D ERRORS HANDLER
@d.error
async def d_error(ctx, error):
    author = ctx.message.author
    help_prefix = prefix_for_help(ctx.message)
    if isinstance(error, commands.BadArgument):
        await ctx.send(f'{author.mention}, wrong dice edge.\n'
                       f'Try something like: ```{help_prefix}d 100```')
    if isinstance(error, commands.ArgumentParsingError):
        await ctx.send(f'{author.mention}, specify valid dice edge, please.\n'
                       f'Try something less than {limits["edge"]}.')
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'{author.mention}, specify valid dice edge, please.\n'
                       f'Try something like: ```{help_prefix}d 20```')


# ROLL COMMAND
@bot_client.command(brief=cmd_brief["roll"], help=cmd_help["roll"], usage=cmd_usage["roll"], aliases=cmd_alias["roll"])
# @bot_client.slash_command(guild_ids=[898524462348115998, 1057983104016465971], brief=cmd_brief["roll"], help=cmd_help["roll"], usage=cmd_usage["roll"], aliases=cmd_alias["roll"])
async def roll(ctx, *arg):
    all_dice = list(arg)
    dice_number = len(all_dice)
    if dice_number == 0:
        author = ctx.message.author
        help_prefix = prefix_for_help(ctx.message)
        await ctx.send(f'{author.mention}, specify valid dice, please.\n'
                       f'Try something like: ```{help_prefix}roll 4d20```')
    check_limit(dice_number, limits["dice"])
    table_body = []

    for dice in all_dice:
        if dice in spec_dice:
            dice = spec_dice[dice]

        # let split our dice roll into number of dices and number of edges
        # 2d20: 2 - number of dices, 20 - number of edges, d - separator
        dice_rolls, dice_edge, dice_type = ident_dice(dice)
        dice_type_len = len(dice_type)

        if dice_type_len == 0:
            dice_roll_result = dice_roll(dice_rolls, dice_edge)
            result = calc_result(dice_roll_result)
        elif dice_type_len == 1 and 'fate' in dice_type:
            dice_roll_result = fate_roll(dice_rolls)
            result = fate_result(dice_roll_result)
        elif dice_type_len == 1 and 'explode' in dice_type:
            dice_roll_result = explode_roll(dice_rolls, dice_edge)
            dice_rolls = 'E' + str(dice_rolls)
            result = calc_result(dice_roll_result)
        else:
            raise commands.BadArgument
        table_dice = dice_maker(dice_rolls, 'd', make_short(dice_edge))
        table_dice_roll_result = make_pretty_rolls(dice_roll_result)
        table_result = make_pretty_sum(result)

        table_row = create_row(table_dice, table_dice_roll_result, table_result)
        table_body.append(table_row)

    output = create_table(table_body)
    # send it into chat
    await ctx.send(f"```{output}```")


# ROLL ERRORS HANDLER
@roll.error
async def roll_error(ctx, error):
    author = ctx.message.author
    help_prefix = prefix_for_help(ctx.message)
    if isinstance(error, commands.BadArgument):
        await ctx.send(f'{author.mention}, wrong dice.\n'
                       f'Try something like: ```{help_prefix}roll d20 5d4 3d10```')
    if isinstance(error, commands.ArgumentParsingError):
        await ctx.send(f'{author.mention}, specify valid dice parameters, please.\n'
                       f'```Current limits:\n'
                       f'- max dice number is {limits["dice"]}\n'
                       f'- max rolls per dice is {limits["roll"]}\n'
                       f'- max dice edge is {limits["edge"]}```')
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'{author.mention}, specify valid dice, please.\n'
                       f'Try something like: ```{help_prefix}roll 4d20```')


# MOD COMMAND
@bot_client.command(brief=cmd_brief["mod"], help=cmd_help["mod"], usage=cmd_usage["mod"], aliases=cmd_alias["mod"])
async def mod(ctx, *arg):
    all_dice = list(arg)
    dice_number = len(all_dice)
    if dice_number == 0:
        author = ctx.message.author
        help_prefix = prefix_for_help(ctx.message)
        await ctx.send(f'{author.mention}, specify valid dice, please.\n'
                       f'Try something like: ```{help_prefix}mod 2d8+1```')
    check_limit(dice_number, limits["dice"])
    table_body = []

    for dice in all_dice:
        if dice in spec_dice:
            dice = spec_dice[dice]

        dice_raw, adds = split_dice_with_mod(dice)
        dice_rolls, dice_edge, dice_type = ident_dice(dice_raw)
        dice_type_len = len(dice_type)

        if dice_type_len == 0:
            dice_roll_result = dice_roll(dice_rolls, dice_edge)
            result = calc_result(dice_roll_result)
        elif dice_type_len == 1 and 'fate' in dice_type:
            dice_roll_result = fate_roll(dice_rolls)
            result = fate_result(dice_roll_result)
        elif dice_type_len == 1 and 'explode' in dice_type:
            dice_roll_result = explode_roll(dice_rolls, dice_edge)
            dice_rolls = 'E' + str(dice_rolls)
            result = calc_result(dice_roll_result)
        else:
            raise commands.BadArgument

        mod_mod = []
        for add in adds:
            try:
                amount = check_int(add[1])
            except Exception:
                rolls, edge, d_type = ident_dice(add[1])
                if len(d_type) != 0:
                    raise commands.BadArgument
                d_result = dice_roll(rolls, edge)
                amount = calc_result(d_result)
            if add[0] == '+':
                result = add_mod_result(result, amount)
            if add[0] == '-':
                if 'fate' in dice_type:
                    result = sub_mod_fate(result, amount)
                else:
                    result = sub_mod_result(result, amount)
            amount_for_table = add[0] + make_short(amount)
            mod_mod.append(amount_for_table)

        table_dice = dice_maker(dice_rolls, 'd', make_short(dice_edge))
        table_dice_roll_result = make_pretty_rolls(dice_roll_result)
        table_mod_list = make_pretty_rolls(mod_mod)
        table_result = make_pretty_sum(result)

        table_row = create_row(table_dice, table_dice_roll_result, table_mod_list, table_result)
        table_body.append(table_row)

    output = create_table(table_body)
    # send it into chat
    await ctx.send(f"```{output}```")


# ROLL ERRORS HANDLER
@mod.error
async def mod_error(ctx, error):
    author = ctx.message.author
    help_prefix = prefix_for_help(ctx.message)
    if isinstance(error, commands.BadArgument):
        await ctx.send(f'{author.mention}, wrong dice.\n'
                       f'Try something like: ```{help_prefix}mod 3d10 d10-1 3d8+1 d100-10```')
    if isinstance(error, commands.ArgumentParsingError):
        await ctx.send(f'{author.mention}, specify valid dice parameters, please.\n'
                       f'```Current limits:\n'
                       f'- max dice number is {limits["dice"]}\n'
                       f'- max rolls per dice is {limits["roll"]}\n'
                       f'- max dice edge is {limits["edge"]}\n'
                       f'- max number of modifiers is {limits["adds"]}\n'
                       f'- max modifier is {limits["mod"]}\n```')
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'{author.mention}, specify valid dice, please.\n'
                       f'Try something like: ```{help_prefix}mod 2d8+1```')


# HELLO COMMAND
@bot_client.command(brief=cmd_brief["hello"], help=cmd_help["hello"], aliases=cmd_alias["hello"])
async def hello(ctx):
    author = ctx.message.author
    help_prefix = prefix_for_help(ctx.message)
    await ctx.send(f'Hello, {author.mention}.\n'
                   f'My name is Dice Roller. '
                   f'I am here to help you with rolling dice. '
                   f'Please, ask "{help_prefix}help" to list commands with short description. '
                   f'Also, ask "{help_prefix}help <command_name>" for more info about each command and examples.')


# ABOUT COMMAND
@bot_client.command(brief=cmd_brief["about"], help=cmd_help["about"], aliases=cmd_alias["about"])
async def about(ctx):
    await ctx.send(f'```Version: 1.1.1\n'
                   f'Author: kreicer\n'
                   f'Github: https://bit.ly/dice_roller_github\n'
                   f'Top.gg: https://bit.ly/dice_roller_vote\n'
                   f'Privacy Policy: https://bit.ly/dice_roller_privacy```')


# STAT COMMAND
@bot_client.command(brief=cmd_brief["stat"], help=cmd_help["stat"], aliases=cmd_alias["stat"])
async def stat(ctx):
    await ctx.send(f'```Statistics:\n'
                   f'Shards: {bot_shards}\n'
                   f'Servers: {guilds_number}```')


# bot start
bot_client.run(settings['token'])

# close sqlite connection
conn.close()
