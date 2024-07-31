import matplotlib.pyplot as plt

# Few cases
# - app downloading dataset (linear, flat)
# - app caching requests up to limit (linear, flat)
# - app going into logging spiral (exponential usage)


usage = [100 for _ in range(0, 40)]+[100 - (i/9)**2 for i in range(0, 160)]
usage = [100-i for i in range(0, 60)]+[40 for _ in range(0, 190)]
curr_values = usage[0:100]
future_values = usage[100:200]

def linear_predict(data: list[float|int], n_values_to_consider, future_len, offset=0) -> tuple[float, float]:
    """
    Linear prediction, calculate slope based on the last `n_values_to_consider` and project
    `future_len` into the future
    """
    dy = data[-n_values_to_consider-offset] - data[-1-offset]
    dx = n_values_to_consider
    predict_duration = future_len+dx
    predicted_value = dy/dx * predict_duration

    return (data[-n_values_to_consider-offset], data[-n_values_to_consider-offset]-predicted_value)

_past=32
_past=16
_past=100
offset=0
linear_predict_60m = linear_predict(curr_values, _past, 100, offset=offset)
predict_x = [len(curr_values)-_past-offset, len(curr_values)+100-offset]

fig = plt.figure()
ax = fig.add_subplot(1, 1, 1)

t = range(0, 100)
t2 = range(100, 200)
ax.plot(t, curr_values, linestyle='solid', color='orange')
ax.plot(t2, future_values, linestyle='dashed', color='orange')
ax.plot(predict_x, linear_predict_60m, linestyle='dashed', color='green')

plt.axvline(100, linestyle=':', color='black')
plt.text(100.1,90,'now',rotation=-90)

ax.set_xlim(0, 200)
ax.set_ylim(0, 110)
plt.show()
