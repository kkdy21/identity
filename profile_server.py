import os
import subprocess
import textwrap
from datetime import datetime

import grpc
from pycallgraph import PyCallGraph
from pycallgraph.config import Config, GlobbingFilter
from pycallgraph.output import GraphvizOutput


class CustomGraphvizOutput(GraphvizOutput):
    """
    A custom outputter that uses subgraph clusters and invisible edges
    to rigidly enforce architectural layering.
    """

    def __init__(self, *args, **kwargs):
        self.custom_rankdir = kwargs.pop("rankdir", "TB")
        super().__init__(*args, **kwargs)
        self.graph_attributes["graph"]["rankdir"] = self.custom_rankdir
        self.graph_attributes["graph"]["newrank"] = "true"

    def node_label(self, node):
        prefix = "spaceone.identity."
        if node.name.startswith(prefix):
            return node.name[len(prefix) :]
        return node.name

    def generate(self):
        indent_join = "\n" + " " * 12
        dot_template = textwrap.dedent("""
        digraph G {{
            // Attributes
            {attributes}

            // Nodes within Clusters
            {nodes}

            // Edges
            {edges}
        }}
        """).strip()

        attributes = indent_join.join(self.generate_attributes())

        layers = {"interface": [], "service": [], "manager": [], "lib": [], "other": []}
        for node in self.processor.nodes():
            layer_found = False
            for layer_name in ["interface", "service", "manager", "lib"]:
                if f".{layer_name}." in node.name:
                    layers[layer_name].append(node)
                    layer_found = True
                    break
            if not layer_found:
                layers["other"].append(node)

        all_nodes_output = []
        layer_order = ["interface", "service", "manager", "lib", "other"]

        for layer_name in layer_order:
            nodes_in_layer = layers[layer_name]
            if not nodes_in_layer:
                continue

            all_nodes_output.append(f'subgraph "cluster_{layer_name}" {{')
            all_nodes_output.append(f'    label = "{layer_name.capitalize()} Layer";')
            all_nodes_output.append('    style = "filled"; color = "lightgrey";')

            for node in nodes_in_layer:
                attr = {
                    "color": self.node_color_func(node).rgba_web(),
                    "label": self.node_label_func(node),
                }
                all_nodes_output.append(f"    {self.node(node.name, attr)}")

            all_nodes_output.append("}")

        invisible_edges = []
        first_nodes = []
        for layer_name in layer_order:
            if layers[layer_name]:
                first_nodes.append(f'"{layers[layer_name][0].name}"')

        if len(first_nodes) > 1:
            invisible_edges.append(
                f"{{ edge [style=invis]; {' -> '.join(first_nodes)}; }}"
            )

        edges_str = indent_join.join(self.generate_edges() + invisible_edges)
        nodes_str = indent_join.join(all_nodes_output)

        return dot_template.format(
            attributes=attributes, nodes=nodes_str, edges=edges_str
        )

    def done(self):
        """
        Generates the graph, saves the DOT file, and then runs the tool to
        render the output file. Captures and prints any errors from the tool.
        """
        source = self.generate()

        dot_filename = self.output_file.replace(".svg", ".dot")
        try:
            with open(dot_filename, "w", encoding="utf-8") as f:
                f.write(source)
            print(f"Successfully saved DOT source to {dot_filename}")
        except IOError as e:
            print(f"Error writing DOT file {dot_filename}: {e}")
            return

        if not self.tool:
            print("Graphviz tool is not specified. Skipping rendering.")
            return

        args = [
            self.tool,
            f"-T{self.output_type}",
            "-o",
            self.output_file,
            dot_filename,
        ]

        try:
            print(f"Running command: {' '.join(args)}")
            result = subprocess.run(args, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                print(f"Successfully generated call graph: {self.output_file}")
            else:
                print(f"Error generating graph with {self.tool}.")
                print(f"Return Code: {result.returncode}")
                if result.stdout:
                    print(f"STDOUT:\n{result.stdout}")
                if result.stderr:
                    print(f"STDERR:\n{result.stderr}")

        except FileNotFoundError:
            print(f"Error: The command '{self.tool}' was not found.")
            print(
                "Please ensure Graphviz is installed and the tool is in your system's PATH."
            )
        except Exception as e:
            print(f"An unexpected error occurred while running {self.tool}: {e}")


class PyCallGraphInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if not (handler and handler.unary_unary):
            return handler

        def profiled_behavior(request, context):
            project_root = os.path.abspath(os.path.dirname(__file__))
            method_name = handler_call_details.method.replace("/", "_").strip("_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_file = os.path.join(
                project_root, f"callgraph_{method_name}_{timestamp}_dot.svg"
            )

            config = Config()
            config.trace_filter = GlobbingFilter(include=["spaceone.identity.*"])

            output = CustomGraphvizOutput(
                output_file=output_file,
                tool="/opt/homebrew/bin/dot",
                output_type="svg",
                rankdir="LR",
            )

            graphviz = PyCallGraph(output=output, config=config)

            print(f"Profiling call: {handler_call_details.method}")
            graphviz.start()
            try:
                response = handler.unary_unary(request, context)
            finally:
                try:
                    graphviz.done()
                except Exception as e:
                    print(f"An error occurred during graph generation: {e}")

            return response

        return grpc.unary_unary_rpc_method_handler(
            profiled_behavior,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


def apply_profiling_interceptor():
    """
    Monkey-patches the grpc.server function to inject the PyCallGraphInterceptor.
    """
    original_grpc_server = grpc.server

    def patched_grpc_server(*args, **kwargs):
        print("Applying PyCallGraphInterceptor via monkey patch...")
        # Original interceptors can be a tuple, which is immutable.
        existing_interceptors = kwargs.get("interceptors", ())

        # Create a new tuple with our interceptor at the beginning.
        new_interceptors = (PyCallGraphInterceptor(),) + existing_interceptors

        # Update the kwargs with the new tuple.
        kwargs["interceptors"] = new_interceptors
        return original_grpc_server(*args, **kwargs)

    grpc.server = patched_grpc_server


def run_server():
    """Imports and runs the gRPC server's main command-line interface."""
    from spaceone.core.command import cli

    command_args = ["run", "grpc-server", "spaceone.identity"]

    # Check if profiling is enabled and apply the patch
    if os.environ.get("SPACEOONE_PROFILE") == "true":
        apply_profiling_interceptor()

    print("Starting gRPC server...")
    cli(command_args, standalone_mode=False)


if __name__ == "__main__":
    run_server()
