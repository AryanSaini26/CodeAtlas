defmodule SampleApp.Utils do
  @doc "Formats a greeting message"
  def greet(name) do
    "Hello, #{name}!"
  end

  @doc "Computes the sum of two numbers"
  def add(a, b) do
    a + b
  end

  defp private_helper(x) do
    x * 2
  end
end

defprotocol SampleApp.Serializable do
  def serialize(data)
end

defmodule SampleApp.Worker do
  def run(items) do
    SampleApp.Utils.greet("world")
    SampleApp.Utils.add(1, 2)
    process(items)
  end

  defp process(items) do
    Enum.map(items, fn x -> x end)
  end
end
