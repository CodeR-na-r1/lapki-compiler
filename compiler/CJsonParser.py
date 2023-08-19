from enum import Enum

try:
    from .SourceFile import SourceFile
    from .fullgraphmlparser.stateclasses import State, Trigger
    from .component import Component
    from .Logger import Logger
    from .RequestError import RequestError
except ImportError:
    from compiler.SourceFile import SourceFile
    from compiler.fullgraphmlparser.stateclasses import State, Trigger
    from compiler.component import Component
    from compiler.Logger import Logger
    from compiler.RequestError import RequestError


class Labels(Enum):
    H_INCLUDE = 'Code for h-file'
    H = 'Declare variable in h-file'
    CPP = 'Code for cpp-file'
    CTOR = 'Constructor code'


class CJsonParser:
    # Переделать под не-статический
    delimeter = {
        "Berloga": "",
        "arduino-cli": ";",
        "gcc": ";",
        "g++": ';'
    }

    operatorAlias = {
        "notEquals": "!=",
        "equals": "==",
        "greater": ">",
        "less": "<",
        "greaterOrEqual": ">=",
        "lessOrEqual": "<=",
        "or": "||",
        "and": "&&"
    }

    @staticmethod
    def initComponent(type: str, name: str, parameters: dict, filename: str):
        """
            Функция, которая в зависимости от компонента
            возвращает код его инициализации.
        """
        match type:
            case 'Timer':
                return f"\n{type} {name} = {type}(the_{filename}, {name}_timeout_SIG);"
            case 'QHsmSerial':
                return f"\n{type} {name} = {type}({', '.join(map(str, list(parameters.values())))}, the_{filename});"
            case _:
                return f"\n{type} {name} = {type}({', '.join(map(str, list(parameters.values())))});"

    @staticmethod
    def specificCheckComponentSignal(type: str, name: str, triggers: dict, filename: str, signal: str) -> str:
        """Функция для специфичных проверок сигналов. Так, например, для
        проверки состояния кнопки необходимо предварительно вызвать функцию scan

        Returns:
            str: специчиная для данного компонента проверка сигнала
        """
        match type:
            case 'Button':
                return '\n\t\t'.join([f"\n\t{name}.scan();\
                        \n\t\n\tif({triggers['guard']})", "{", f"SIMPLE_DISPATCH(the_{filename}, {signal});\n\t"]) + "\n\t}"
            case "Timer":
                return f"\n\t{name}.timeout();"
            case _:
                return '\n\t\t'.join([f"\n\t\n\tif({triggers['guard']})", "{", f"SIMPLE_DISPATCH(the_{filename}, {signal});"]) + "\n\t}"

    @staticmethod
    async def appendNote(label: Labels, content, notes):
        notes.append({"y:UMLNoteNode":
                      {'y:NodeLabel':
                       {"#text": f'{label.value}: {content}'}}})

    @staticmethod
    async def getLibraries(components) -> list[str]:
        libraries = []
        for component in components:
            if component.type not in libraries:
                libraries.append(f"{component.type}")

        return libraries

    @staticmethod
    def setupVariables(name: str, type: str) -> str | None:
        match type:
            case "QHsmSerial":
                return f"{name}.init();"
            case "DigitalOut":
                return f"{name}.init();"

        return None

    @staticmethod
    def actionInMain(component: Component, signals: list[str]) -> None:
        match component.type:
            case "AnalogIn":
                signals.append(
                    f"\n\t{component.name}.read();")

    @staticmethod
    async def createNotes(components: list[Component], filename: str, triggers: dict, compiler: str, path) -> list:
        includes = []
        variables = []
        setup = []
        components_types = {}
        types = []
        setup_variables: list[str] = []
        check_signals = []

        for component in components:
            components_types[component.name] = component.type
            if component.type not in types:
                includes.append(f'\n#include "{component.type}.h"')
                types.append(component.type)

            CJsonParser.actionInMain(component, check_signals)
            setup_variable = CJsonParser.setupVariables(
                component.name, component.type)
            if setup_variable:
                setup_variables.append(setup_variable)
            variables.append(CJsonParser.initComponent(component.type,
                                                       component.name,
                                                       component.parameters,
                                                       filename))
        notes = []

        class_filename = filename[0].upper() + filename[1:]

        for name in triggers.keys():
            component_name = triggers[name]["component_name"]
            component_type = components_types[component_name]
            check = CJsonParser.specificCheckComponentSignal(name=component_name,
                                                             type=component_type,
                                                             triggers=triggers[name],
                                                             filename=filename,
                                                             signal=name)
            check_signals.append(check)

        print(check_signals)
        match compiler:
            case "g++" | "gcc":
                setup_function = '\n\t'.join(["\nvoid setup(){",
                                              *setup,
                                              "\n}"])

                loop_function = ''.join(["\nvoid loop(){", *check_signals,
                                        "\n}"])

                main_function = '\n\t'.join(["\nint main(){",
                                            f"{class_filename}_ctor();",
                                             "QEvt event;",
                                             f"QMsm_init(the_{filename}, &event);",
                                             "setup();",
                                             "while(true){",
                                             "\tloop();",
                                             "}"]) + "\n}"
                await CJsonParser.appendNote(Labels.H, "".join(variables), notes)
                await CJsonParser.appendNote(Labels.H_INCLUDE, "".join(includes), notes)
                await CJsonParser.appendNote(Labels.CPP, "\n\n".join([setup_function, loop_function, main_function]), notes)

            case "arduino-cli":
                setup_function = '\n\t'.join(["\nvoid setup(){",
                                              *setup_variables,
                                              f"{class_filename}_ctor();",
                                              "QEvt event;",
                                              f"QMsm_init(the_{filename}, &event);",
                                              "\n}"])
                loop_function = ''.join(
                    ["\nvoid loop(){", *check_signals, "\n}"])
                await CJsonParser.appendNote(Labels.H, "".join(variables), notes)
                await CJsonParser.appendNote(Labels.H_INCLUDE, "".join(includes), notes)
                await CJsonParser.appendNote(Labels.CPP, "\n\n".join([setup_function, loop_function]), notes)

        return notes

    @staticmethod
    async def getComponents(components: list) -> list[Component]:
        result = []

        for component_name in components:
            result.append(Component(
                component_name, type=components[component_name]["type"], parameters=components[component_name]["parameters"]))

        return result

    @staticmethod
    async def getCondition(condition_dict: dict, compiler: str, condition: list = []) -> str:
        type: str = condition_dict["type"]
        if type in list(CJsonParser.operatorAlias.keys()):
            values = []
            for value in condition_dict["value"]:
                values.append(await CJsonParser.getCondition(value, compiler=compiler))
            result = f" {CJsonParser.operatorAlias[type]} ".join(
                map(str, values))
            return result
        elif type == "value":
            return str(condition_dict["value"])
        elif type == "component":
            component = condition_dict["value"]["component"] + "."
            method = condition_dict["value"]["method"]

            # В Берлоге в условиях используются
            # только числа и поля класса!
            args = ""
            if compiler != "Berloga":
                arr_args = []
                if args in condition_dict.keys():
                    arr_args = list(condition_dict["args"].values())
                args = "(" + ",".join(map(str, arr_args)) + ")"

            return "".join([component, method, args])
        return "true"

    @staticmethod
    async def getActions(actions: list[dict], compiler: str) -> str:
        result: list[str] = []
        for action in actions:
            component = action["component"]
            method = "." + action["method"]
            arr_args = []
            if "args" in action.keys():
                for act in list(action["args"].values()):
                    if type(act) is str:
                        arr_args.append(act)
                    elif type(act) is dict:
                        arr_args.append(f'{act["component"]}.{act["method"]}')
            args = "(" + ",".join(map(str, arr_args)) + ")" + \
                CJsonParser.delimeter[compiler]
            result.append("".join([component, method, args]))

        return "\n".join(result)

    @staticmethod
    async def getTransitions(transitions: list[dict], compiler: str):
        result = []
        player_signals = {}
        i = 0
        for transition in transitions:
            guard = ''.join([transition["trigger"]["component"], '.',
                             transition["trigger"]["method"], '('])
            arr_args = []
            if "args" in transition["trigger"].keys():
                arr_args = list(transition["trigger"]["args"].values())
                guard += ','.join(arr_args)
            guard += ')'

            name = ''.join([transition["trigger"]["component"], '_',
                            transition["trigger"]["method"]]) + "_".join(arr_args)

            trig = {}
            player_signals[name] = {}
            player_signals[name]["guard"] = guard
            player_signals[name]["component_name"] = transition["trigger"]["component"]
            if "condition" in transition.keys() and transition["condition"] is not None:
                root = transition["condition"]
                condition = await CJsonParser.getCondition(root, compiler)
            else:
                condition = "true"
            if "do" in transition.keys():
                action = await CJsonParser.getActions(transition["do"],
                                                      compiler)
            else:
                action = ""
            trig["trigger"] = Trigger(name=name, source=transition["source"],
                                      target=transition["target"], id=i,
                                      type="external", guard=condition,
                                      action=action, points=[])

            result.append(trig)
            i += 1
        return result, player_signals

    @staticmethod
    async def getEvents(events: list[dict[str, dict[str, str] | str]], statename: str, compiler: str) -> tuple[dict[str, Trigger], dict[str, str], dict[str, str]]:
        result = {}
        id = 0
        event_signals = {}
        system_signals = {
            "onEnter": "",
            "onExit": ""
        }
        for event in events:
            trigger = event["trigger"]
            component = trigger["component"]
            method = trigger["method"]

            actions = ""
            for i in range(len(event["do"])):
                actions += event["do"][i]["component"] + \
                    '.' + event["do"][i]["method"] + '('
                if "args" in event["do"][i].keys():
                    arr_action = []
                    for arg in list(event["do"][i]["args"].values()):
                        if type(arg) is str:
                            arr_action.append(arg)
                        elif type(arg) is dict:
                            arr_action.append(
                                f'{arg["component"]}.{arg["method"]}')
                    actions += ','.join(map(str, arr_action))
                actions += ")" + CJsonParser.delimeter[compiler] + "\n"

            if component != "System":
                eventname = component + '_' + method
                guard = ''.join([component, '.', method, "()"])
                event_signals[eventname] = {}
                event_signals[eventname]["guard"] = guard
                event_signals[eventname]["component_name"] = trigger["component"]

                trig = Trigger(name=eventname, type="internal", source=statename,
                               target="", action=actions, id=id,
                               points=[])
                id += 1
                result[eventname] = trig
            else:
                system_signals[method] = actions
        return (result, event_signals, system_signals)

    @staticmethod
    async def addParentsAndChilds(states, processed_states, global_state):
        result = processed_states.copy()
        for statename in states:
            state = states[statename]
            try:
                result[statename].parent = result[state["parent"]]
                result[state["parent"]].childs.append(result[statename])
            except KeyError:
                result[statename].parent = global_state
                global_state.childs.append(result[statename])

        return result

    @staticmethod
    async def addTransitionsToStates(transitions, states):
        new_states = states.copy()
        for transition in transitions:
            new_states[transition["trigger"].source].trigs.append(
                transition["trigger"])

        return new_states

    @staticmethod
    async def getGeometry(state: dict) -> tuple[int, int, int, int]:
        x = state["bounds"]["x"]
        y = state["bounds"]["y"]
        try:
            w = state["bounds"]["width"]
            h = state["bounds"]["height"]
        except KeyError:
            w = 100
            h = 100

        return x, y, w, h

    @staticmethod
    def addSignals(components: list[Component], player_signals: list[str]) -> list[str]:
        types: set[str] = set()
        signals: list[str] = []
        for component in components:
            match component.type:
                case "QHsmSerial":
                    if component.type not in types:
                        signals.append("SERIAL_NO_DATA_RECEIVED")
                        signals.append("SERIAL_RECEIVED_BYTE")
                case "Timer":
                    if component.type not in types and f"{component.name}_timeout" not in player_signals:
                        signals.append(f"{component.name}_timeout")
        return signals

    @staticmethod
    async def parseStateMachine(json_data, ws, filename="", compiler="", path=None):
        try:
            global_state = State(name="global", type="group",
                                 actions="", trigs=[],
                                 entry="", exit="",
                                 id="global", new_id=["global"],
                                 parent=None, childs=[])
            states = json_data["states"]
            proccesed_states = {}
            event_signals = {}
            for statename in states:
                state = json_data["states"][statename]
                events, new_event_signals, system_signals = await CJsonParser.getEvents(state["events"], statename, compiler)
                event_signals = dict(
                    list(new_event_signals.items()) + list(event_signals.items()))

                on_enter = system_signals["onEnter"]
                on_exit = system_signals["onExit"]

                x, y, w, h = await CJsonParser.getGeometry(state)
                proccesed_states[statename] = State(name=state["name"], type="state",
                                                    actions="", trigs=list(events.values()),
                                                    entry=on_enter, exit=on_exit,
                                                    id=statename, new_id=[
                                                        statename],
                                                    parent=None, childs=[],
                                                    x=x, y=y,
                                                    width=w, height=h)
            transitions, player_signals = await CJsonParser.getTransitions(json_data["transitions"], compiler)
            player_signals = dict(
                list(player_signals.items()) + list(event_signals.items()))
            components = await CJsonParser.getComponents(json_data["components"])
            if compiler in ["arduino-cli", "g++", "gcc"]:
                notes = await CJsonParser.createNotes(components, filename, player_signals, compiler=compiler, path=path)
            else:
                notes = []
            startNode = proccesed_states[json_data["initialState"]].id
            proccesed_states = await CJsonParser.addTransitionsToStates(transitions, proccesed_states)
            proccesed_states = await CJsonParser.addParentsAndChilds(states, proccesed_states, global_state)
            return {"states": [global_state, *list(proccesed_states.values())],
                    "notes": notes,
                    "startNode": startNode,
                    "playerSignals": [*player_signals.keys(),
                                      *CJsonParser.addSignals(components, player_signals)]}
        except KeyError as e:
            await RequestError(f"There isn't key('{e.args[0]}') ").dropConnection(ws)
            await Logger.logException()
        except Exception:
            await Logger.logException()

    @staticmethod
    async def getFiles(json_data):
        files = []

        for data in json_data:
            files.append(SourceFile(
                data["filename"], data["extension"], data["fileContent"]))

        return files
