import os
import click
import re
from fnmatch import fnmatch
from .guidance import Model, assistant, system, user

def should_ignore(path, gitignore_rules):
    for rule in gitignore_rules:
        if fnmatch(os.path.basename(path), rule):
            return True
        if os.path.isdir(path) and fnmatch(os.path.basename(path) + "/", rule):
            return True
    return False


def read_gitignore(path):
    gitignore_path = os.path.join(path, ".gitignore")
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r") as f:
            return [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
    return []


def process_path(
    path, include_hidden, ignore_gitignore, gitignore_rules, ignore_patterns
):
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                file_contents = f.read()
                summary = summarize_file(file_contents) 
            click.echo(path)
            click.echo("---")
            click.echo(summary)
            click.echo()
            click.echo("---")
        except UnicodeDecodeError:
            warning_message = f"Warning: Skipping file {path} due to UnicodeDecodeError"
            click.echo(click.style(warning_message, fg="red"), err=True)
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]

            if not ignore_gitignore:
                gitignore_rules.extend(read_gitignore(root))
                dirs[:] = [
                    d
                    for d in dirs
                    if not should_ignore(os.path.join(root, d), gitignore_rules)
                ]
                files = [
                    f
                    for f in files
                    if not should_ignore(os.path.join(root, f), gitignore_rules)
                ]

            if ignore_patterns:
                files = [
                    f
                    for f in files
                    if not any(fnmatch(f, pattern) for pattern in ignore_patterns)
                ]

            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r") as f:
                        file_contents = f.read()
                        summary = summarize_file(file_contents) 

                    click.echo(file_path)
                    click.echo("---")
                    click.echo(summary)
                    click.echo()
                    click.echo("---")
                except UnicodeDecodeError:
                    warning_message = (
                        f"Warning: Skipping file {file_path} due to UnicodeDecodeError"
                    )
                    click.echo(click.style(warning_message, fg="red"), err=True)


@click.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--include-hidden",
    is_flag=True,
    help="Include files and folders starting with .",
)
@click.option(
    "--ignore-gitignore",
    is_flag=True,
    help="Ignore .gitignore files and include all files",
)
@click.option(
    "ignore_patterns",
    "--ignore",
    multiple=True,
    default=[],
    help="List of patterns to ignore",
)
@click.version_option()
def cli(paths, include_hidden, ignore_gitignore, ignore_patterns):
    """
    Takes one or more paths to files or directories and outputs every file,
    recursively, each one preceded with its filename like this:

    path/to/file.py
    ----
    Contents of file.py goes here

    ---
    path/to/file2.py
    ---
    ...
    """
    gitignore_rules = []
    for path in paths:
        if not os.path.exists(path):
            raise click.BadArgumentUsage(f"Path does not exist: {path}")
        if not ignore_gitignore:
            gitignore_rules.extend(read_gitignore(os.path.dirname(path)))
        process_path(
            path, include_hidden, ignore_gitignore, gitignore_rules, ignore_patterns
        )

def trim_indent(text: str) -> str:
    # Remove leading spaces from each line
    output = re.sub(r'^[ ]+', '', text, flags=re.M)

    # Check and remove the first character if it is a newline
    if output.startswith('\n'):
        output = output[1:]

    # Check and remove the last character if it is a newline
    if output.endswith('\n'):
        output = output[:-1]

    return output

def estimate_num_words(sentence):
    words = sentence.split()
    return len(words)

def summarize_file(contents : str) -> str:
    if estimate_num_words(contents) > 30: 
        llm = Model("gpt-4-turbo")
        with system():
            llm += trim_indent(f"""
            Objective:
            Create a summarized version of the given code file that includes only the types, interfaces, and function definitions that are exported (visible outside the file/module). Include explanatory comments for each exported function and type.

            **Instructions:**

            Exclude:
            - All import statements.
            - All function bodies.
            - Any type, interface, or function that is not exported (i.e., starts with a lowercase letter in Go or is prefixed with an underscore in Python).


            Include:
            - Full definitions of any exported types and data structures.
            - Exported function definitions without bodies.
            - Concise explanatory comments for each exported function and type.

            **Comments:**
            - Write a comment at the top summarizing the file's purpose.
            - Explain each function's purpose, and briefly inputs and outputs.
            """)
        with user():
            llm += trim_indent("""
                package ast

                import (
	                "bufio"
                    "io"
                )

                type prefs struct {
                    reader NamedReader
                }

                type NamedReader interface {
                    Read(buff []byte) (n int, err error)
                }

                type Opt func(prefs) (prefs, error)

                func WithSourceMap() Opt {
                    return func(p prefs) (prefs, error) {
                        return p, nil
                    }
                }

                func FromPath(path string) (prefs, error) {
                    var p prefs
                    f, err := os.Open(path)
                    if err != nil {
                        return p, err
                    }
                    p.reader = f
                    return p, nil
                }
                               """)
        with assistant():
            llm += trim_indent("""
                package ast

                // Parses configurations for a version parser. Defines options (`Opt` and `FromOpt`) to customize parsing behavior, such as enabling a source map or specifying the data source. Contains `prefs` structure for configurations and `NamedReader` interface for reading sources.

                // holds parsing configuration settings.
                type prefs struct {
                    reader NamedReader  // data source
                }

                // an io.Reader with additional methods.
                type NamedReader interface {
                    Read(buff []byte) (n int, err error)
                }

                // for modifying parsing preferences.
                type Opt func(prefs) (prefs, error)

                // source mapping in preferences.
                func WithSourceMap() Opt { ... }

                // tell parser to read from a file path.
                func FromPath(path string) (prefs, error) { ... }
                               """)
        with user():
            llm += contents
        with assistant():
            llm.gen('answer', 4096)
        return llm["answer"]
    return contents
